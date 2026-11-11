"""Coleta diária: baixa boletins novos, guarda no banco, normaliza e gera docs/dados.json.

Uso:
    python -m coleta.run                          # todas as CEASAs, últimos 30 dias
    python -m coleta.run --ceasa ES --inicio 2026-01-01 --max 200
    python -m coleta.run --discover ES            # inspeciona o formulário (sem banco)
"""
import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

from . import db
from .ceasas import REGISTRO
from .exportar import exportar

BRT = dt.timezone(dt.timedelta(hours=-3))  # Brasília (sem horário de verão)
SAIDA = Path("saida")  # boletins brutos e diagnósticos (vira artefato no GitHub Actions)


def agora():
    return dt.datetime.now(BRT).strftime("%H:%M:%S")


def log(*partes):
    print(f"{agora()}", *partes, flush=True)


def lista_datas(datas):
    """'2026-01-02, 2026-01-05, ...' em linhas de 8 datas, para o log ficar legível."""
    ds = [d.isoformat() for d in datas]
    return "\n".join("      " + ", ".join(ds[i:i + 8]) for i in range(0, len(ds), 8))


def coletar(c, page, conn, inicio, fim, maximo):
    feitas = db.datas_resolvidas(conn, c.id)
    no_site = c.datas(page)
    pend = [(d, ref) for d, ref in no_site if inicio <= d <= fim and d not in feitas]
    lote = pend[:maximo]
    log(f"[{c.id}] datas no site: {len(no_site)}"
        + (f" (de {min(d for d, _ in no_site)} a {max(d for d, _ in no_site)})" if no_site else ""))
    log(f"[{c.id}] período pedido: {inicio} a {fim} | já coletadas: {len([d for d in feitas if inicio <= d <= fim])} "
        f"| pendentes: {len(pend)}")
    if not lote:
        log(f"[{c.id}] nada a coletar: todas as datas do período já foram coletadas")
        return
    log(f"[{c.id}] NESTA EXECUÇÃO vou coletar {len(lote)} boletins, de {lote[0][0]} a {lote[-1][0]}:")
    print(lista_datas([d for d, _ in lote]), flush=True)
    if len(pend) > len(lote):
        log(f"[{c.id}] ficarão {len(pend) - len(lote)} pendentes (de {pend[len(lote)][0]} a {pend[-1][0]}) "
            f"para a próxima execução")
    cont = {"ok": 0, "sem_dados": 0, "erro": 0}
    seguidos = 0
    for n, (d, ref) in enumerate(lote, 1):
        log(f"[{c.id}] ({n}/{len(lote)}) coletando {d} ...")
        t0 = dt.datetime.now()
        try:
            res = c.capturar(page, ref)
            seguidos = 0
        except Exception as e:  # noqa: BLE001
            seguidos += 1
            cont["erro"] += 1
            db.gravar_boletim(conn, c.id, d, "erro", erro=str(e)[:500])
            log(f"[{c.id}] ({n}/{len(lote)}) {d} ERRO: {e}")
            if seguidos >= 3:  # site provavelmente fora do ar: para e tenta na próxima execução
                log(f"[{c.id}] 3 erros seguidos; parando. Continua na próxima execução.")
                break
            continue
        seg = (dt.datetime.now() - t0).total_seconds()
        if not res:
            cont["sem_dados"] += 1
            db.gravar_boletim(conn, c.id, d, "sem_dados")
            log(f"[{c.id}] ({n}/{len(lote)}) {d} sem boletim no site ({seg:.0f}s)")
            continue
        bruto, ext, linhas = res
        pasta = SAIDA / c.id
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{d}.{ext}").write_bytes(bruto)
        db.gravar_boletim(conn, c.id, d, "ok", hashlib.sha256(bruto).hexdigest(), linhas)
        cont["ok"] += 1
        log(f"[{c.id}] ({n}/{len(lote)}) {d} OK: {len(linhas)} linhas gravadas ({seg:.0f}s)")
        page.wait_for_timeout(1500)  # pausa educada com o servidor
    feitos = cont["ok"] + cont["sem_dados"] + cont["erro"]
    log(f"[{c.id}] RESUMO: {cont['ok']} coletados, {cont['sem_dados']} sem boletim, {cont['erro']} com erro "
        f"({feitos} de {len(lote)} tentados); faltam {len(pend) - cont['ok'] - cont['sem_dados']} no período")


def normalizar(conn, c):
    pend = db.pendentes_normalizacao(conn, c.id)
    n = 0
    for d in pend:
        brutas = db.linhas(conn, c.id, d)
        if not brutas:  # boletim antigo sem linhas guardadas: mantém as cotações que já existem
            print(f"[{c.id}] {d}: sem linhas brutas guardadas, cotações existentes mantidas")
            continue
        cots = c.normalizar(brutas, d)
        if cots is None:
            print(f"[{c.id}] parser ainda não implementado: {len(pend)} boletins aguardando normalização")
            return
        db.gravar_cotacoes(conn, c.id, d, cots)
        n += 1
        log(f"[{c.id}] normalizado {d}: {len(cots)} cotações ({sum(1 for x in cots if x['conferencia'] == 'validado')} validadas)")
    if n:
        log(f"[{c.id}] {n} boletins normalizados")


def main():
    sys.stdout.reconfigure(line_buffering=True)   # no GitHub Actions o log aparece na hora, não só no fim
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--ceasa", nargs="*", help="IDs (padrão: todas do registro)")
    ap.add_argument("--inicio", help="AAAA-MM-DD (padrão: 30 dias atrás)")
    ap.add_argument("--max", type=int, default=40, help="máx. boletins novos por CEASA nesta execução")
    ap.add_argument("--json", default="docs/dados.json", help="arquivo de saída do app")
    ap.add_argument("--discover", metavar="ID", help="inspeciona o formulário de uma CEASA e sai")
    ap.add_argument("--diagnostico", action="store_true", help="testa se o site das CEASAs abre (computador x Android) e sai")
    ap.add_argument("--perfil", choices=["computador", "android"], default="computador", help="navegador que a coleta simula")
    ap.add_argument("--renormalizar", action="store_true", help="refaz a padronização de todos os boletins já baixados (sem baixar de novo)")
    ap.add_argument("--headed", action="store_true", help="mostra o navegador (uso local)")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    SAIDA.mkdir(exist_ok=True)
    if a.diagnostico:
        from . import diagnostico
        with sync_playwright() as p:
            diagnostico.rodar(p, SAIDA)
        return 0

    def contexto(browser, **kw):
        if a.perfil == "android":
            kw = {**browser_p.devices["Pixel 7"], **kw}   # celular Android simulado
        return browser.new_context(ignore_https_errors=True, **kw)

    if a.discover:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not a.headed)
            browser_p = p
            REGISTRO[a.discover].discover(contexto(browser).new_page(), SAIDA)
            browser.close()
        return 0

    ids = a.ceasa or list(REGISTRO)
    desconhecidas = [i for i in ids if i not in REGISTRO]
    if desconhecidas:
        raise SystemExit(f"CEASA sem coletor: {desconhecidas}. Disponíveis: {list(REGISTRO)}")
    alvo = [REGISTRO[i] for i in ids]
    hoje = dt.datetime.now(BRT).date()
    inicio = dt.date.fromisoformat(a.inicio) if a.inicio else hoje - dt.timedelta(days=30)

    conn = db.conectar()
    db.registrar_ceasas(conn, alvo)
    if a.renormalizar:
        for c in alvo:
            db.renormalizar(conn, c.id)
    falhas = 0
    with sync_playwright() as p:
        browser_p = p
        browser = p.chromium.launch(headless=not a.headed)
        for c in ([] if a.renormalizar else alvo):  # uma CEASA com problema não derruba as outras
            ctx = contexto(browser, accept_downloads=True)  # o site usa certificado de IP
            try:
                coletar(c, ctx.new_page(), conn, inicio, hoje, a.max)
            except Exception as e:  # noqa: BLE001
                falhas += 1
                print(f"[{c.id}] FALHOU: {e}")
            finally:
                ctx.close()
        browser.close()

    for c in alvo:
        normalizar(conn, c)
    exportar(conn, a.json)
    conn.close()
    return 1 if (falhas == len(alvo) and not a.renormalizar) else 0  # erro só se todas falharem (o GitHub avisa por e-mail)


if __name__ == "__main__":
    sys.exit(main())
