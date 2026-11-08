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


def coletar(c, page, conn, inicio, fim, maximo):
    feitas = db.datas_resolvidas(conn, c.id)
    pend = [(d, ref) for d, ref in c.datas(page) if inicio <= d <= fim and d not in feitas]
    print(f"[{c.id}] {len(pend)} boletins pendentes ({inicio} a {fim}); "
          f"baixando até {min(maximo, len(pend))} nesta execução")
    seguidos = 0
    for d, ref in pend[:maximo]:
        try:
            res = c.capturar(page, ref)
            seguidos = 0
        except Exception as e:  # noqa: BLE001
            seguidos += 1
            db.gravar_boletim(conn, c.id, d, "erro", erro=str(e)[:500])
            print(f"[{c.id}] {d} erro: {e}")
            if seguidos >= 3:  # site provavelmente fora do ar: para e tenta na próxima execução
                print(f"[{c.id}] 3 erros seguidos; parando. Continua na próxima execução.")
                break
            continue
        if not res:
            db.gravar_boletim(conn, c.id, d, "sem_dados")
            print(f"[{c.id}] {d} sem dados no site")
            continue
        bruto, ext, linhas = res
        pasta = SAIDA / c.id
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{d}.{ext}").write_bytes(bruto)
        db.gravar_boletim(conn, c.id, d, "ok", hashlib.sha256(bruto).hexdigest(), linhas)
        print(f"[{c.id}] {d} ok ({len(linhas)} linhas)")
        page.wait_for_timeout(1500)  # pausa educada com o servidor


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
    if n:
        print(f"[{c.id}] {n} boletins normalizados")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--ceasa", nargs="*", help="IDs (padrão: todas do registro)")
    ap.add_argument("--inicio", help="AAAA-MM-DD (padrão: 30 dias atrás)")
    ap.add_argument("--max", type=int, default=40, help="máx. boletins novos por CEASA nesta execução")
    ap.add_argument("--json", default="docs/dados.json", help="arquivo de saída do app")
    ap.add_argument("--discover", metavar="ID", help="inspeciona o formulário de uma CEASA e sai")
    ap.add_argument("--renormalizar", action="store_true", help="refaz a padronização de todos os boletins já baixados (sem baixar de novo)")
    ap.add_argument("--headed", action="store_true", help="mostra o navegador (uso local)")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright

    SAIDA.mkdir(exist_ok=True)
    if a.discover:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not a.headed)
            REGISTRO[a.discover].discover(browser.new_context(ignore_https_errors=True).new_page(), SAIDA)
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
        browser = p.chromium.launch(headless=not a.headed)
        for c in ([] if a.renormalizar else alvo):  # uma CEASA com problema não derruba as outras
            ctx = browser.new_context(accept_downloads=True, ignore_https_errors=True)  # o site usa certificado de IP
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
