"""Monitor de horário de publicação dos boletins das CEASAs.

Nenhuma CEASA informa a hora em que publica o boletim. Este monitor abre a página de cada uma
a cada 10 minutos (dias úteis, 05:20–21:00 de Brasília) e grava no banco uma "assinatura" do que
está publicado (links de boletins e datas que aparecem na página). Quando a assinatura muda,
saiu boletim novo: o horário dessa verificação é o horário de publicação (precisão de ~10 min).

  python -m coleta.monitor                     # roda até o fim da janela atual (11:20, 17:20 ou 21:00)
  python -m coleta.monitor --uma-vez           # uma rodada só (teste)
  python -m coleta.monitor --relatorio --desde 2026-11-25    # tabela mín./máx./mais comum

ES e BA usam os coletores do projeto (data do boletim mais recente disponível). O RJ bloqueia
os servidores do GitHub e fica de fora (só funcionaria no runner do seu computador).
"""
import argparse
import datetime as dt
import hashlib
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict

from . import db

BRT = dt.timezone(dt.timedelta(hours=-3))
FIM_JANELAS = [(11, 20), (17, 20), (21, 0)]   # cada execução agendada vai até a próxima destas horas
INTERVALO = 600                               # 10 min

# (id, nome, página onde o boletim aparece) — da planilha base_ceasas_brasil
FONTES = [
    ("CE", "CEASA Maracanaú (CE)", "https://www.ce.gov.br/ceasa-ce/html/boletim-diario-de-precos/"),
    ("DF", "CEASA Brasília (DF)", "https://www.portal.ceasadf.com.br/informacao-mercado"),
    ("GO", "CEASA Goiânia (GO)", "https://goias.gov.br/ceasa/cotacoes-diarias/"),
    ("MG", "CEASAMINAS Contagem (MG)", "https://www.ceasaminas.com.br/informacoesmercado/contator_boletimdiarioprecos.asp"),
    ("MT", "CEASA Cuiabá (MT)", "https://www.agriculturafamiliar.mt.gov.br/prohort2"),
    ("PA", "CEASA Belém (PA)", "https://www.ceasa.pa.gov.br/cotacoes"),
    ("PE", "CEASA Recife (PE)", "https://www.ceasape.org.br/cotacao"),
    ("PR", "CEASA Curitiba (PR)", "https://www.ceasa.pr.gov.br/Pagina/Cotacao-Diaria-de-Precos-2026"),
    ("RN", "CEASA Grande Natal (RN)", "https://transparencia.ceasa.rn.gov.br/cotacoes"),
    ("RS", "CEASA Porto Alegre (RS)", "https://www.ceasa.rs.gov.br/cotacoes-de-precos"),
    ("SC", "CEASA São José (SC)", "https://www.ceasa.sc.gov.br/index.php/cotacao-de-precos"),
    ("SE", "CEASA Aracaju (SE)", "https://emdagro.se.gov.br/precos-medios-semanais-atacado-e-varejo/"),
    ("SP", "CEAGESP São Paulo (SP)", "https://ceagesp.gov.br/cotacoes/"),
]
NOMES = {"ES": "CEASA Grande Vitória (ES)", "BA": "CEASA Salvador (BA)", **{f[0]: f[1] for f in FONTES}}

LINK_BOLETIM = re.compile(r"\.(pdf|xlsx?|csv)(\?|$)|boletim|cota[çc]|pre[çc]o|\d{1,2}[-_/.]\d{1,2}[-_/.]\d{2,4}", re.I)
LINK_LIXO = re.compile(r"facebook|instagram|twitter|youtube|whatsapp|linkedin|login|javascript:|mailto:", re.I)
DATA = re.compile(r"\b(\d{2})/(\d{2})/(20\d{2})\b")

SQL_TABELA = """CREATE TABLE IF NOT EXISTS monitor_publicacao (
    fonte TEXT NOT NULL, verificado_em TEXT NOT NULL, ok BOOLEAN NOT NULL,
    assinatura TEXT, info TEXT)"""


def agora():
    return dt.datetime.now(BRT)


def _hash(txt):
    return hashlib.sha256(txt.encode()).hexdigest()[:16]


def assinatura_pagina(page, url):
    """Links de boletim/cotação + datas visíveis na página -> (assinatura, resumo)."""
    r = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if r and r.status >= 400:
        raise RuntimeError(f"HTTP {r.status}")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:  # noqa: BLE001 (páginas que nunca "assentam")
        pass
    links = page.eval_on_selector_all(
        "a[href]", "els => els.map(a => [a.href.split('#')[0], (a.textContent || '').trim().slice(0, 80)])")
    rel = sorted({h for h, t in links if LINK_BOLETIM.search(f"{h} {t}") and not LINK_LIXO.search(h)})
    texto = page.inner_text("body")
    datas = sorted({f"{a}-{m}-{d}" for d, m, a in DATA.findall(texto)})
    hoje = agora().date().isoformat()
    datas = [d for d in datas if d != hoje]   # "hoje é dd/mm" no topo da página não é boletim novo
    base = "\n".join(rel) + "\n--\n" + "\n".join(datas)
    return _hash(base), f"{len(rel)} links; última data {datas[-1] if datas else '-'}"


def rodada(browser, conn):
    from .ceasas import REGISTRO
    from .ceasas.ba import links_do_html

    def gravar(fonte, ok, ass, info):
        conn.executar("INSERT INTO monitor_publicacao (fonte, verificado_em, ok, assinatura, info) "
                      "VALUES (%s, %s, %s, %s, %s)", (fonte, agora().isoformat(timespec="seconds"), ok, ass, info))
        conn.commit()
        print(f"{agora():%H:%M:%S} {fonte:3} {'ok ' if ok else 'ERRO'} {ass or ''} {info}", flush=True)

    # ES e BA: data do boletim mais recente, pelos coletores do projeto
    for cid in ("ES", "BA"):
        c = REGISTRO[cid]
        ctx = browser.new_context(ignore_https_errors=True, **getattr(c, "contexto", {}))
        try:
            ultima = max(d for d, _ in c.datas(ctx.new_page()))
            gravar(cid, True, ultima.isoformat(), f"último boletim {ultima:%d/%m/%Y}")
        except Exception as e:  # noqa: BLE001
            gravar(cid, False, None, str(e).splitlines()[0][:200])
        finally:
            ctx.close()
    # demais: assinatura da página
    for fid, _nome, url in FONTES:
        ctx = browser.new_context(ignore_https_errors=True, locale="pt-BR")
        try:
            ass, info = assinatura_pagina(ctx.new_page(), url)
            gravar(fid, True, ass, info)
        except Exception as e:  # noqa: BLE001
            gravar(fid, False, None, str(e).splitlines()[0][:200])
        finally:
            ctx.close()


def fim_da_janela(t):
    for h, m in FIM_JANELAS:
        fim = t.replace(hour=h, minute=m, second=0, microsecond=0)
        if fim > t + dt.timedelta(minutes=5):
            return fim
    return t


def monitorar(uma_vez=False):
    from playwright.sync_api import sync_playwright

    conn = db.conectar()
    conn.executar(SQL_TABELA)
    conn.commit()
    fim = fim_da_janela(agora())
    print(f"Monitorando até {fim:%H:%M} (Brasília), a cada {INTERVALO // 60} min")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        while True:
            inicio = time.time()
            try:
                rodada(browser, conn)
            except Exception as e:  # noqa: BLE001  (o Neon fecha conexão parada; reconecta e segue)
                print(f"{agora():%H:%M} conexão com o banco perdida ({str(e).splitlines()[0]}); reconectando")
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
                try:   # se falhar de novo, pula esta rodada em vez de derrubar o monitor inteiro
                    conn = db.conectar()
                    rodada(browser, conn)
                except Exception as e2:  # noqa: BLE001
                    print(f"{agora():%H:%M} rodada perdida ({str(e2).splitlines()[0]}); tenta na próxima")
            if uma_vez:
                break
            prox = inicio + INTERVALO
            if dt.datetime.fromtimestamp(prox, BRT) >= fim:
                break
            time.sleep(max(0, prox - time.time()))
        browser.close()
    conn.close()


# ---------------- relatório ----------------
def publicacoes(linhas):
    """[(fonte, verificado_em, ok, assinatura)] -> {fonte: {dia: hora da 1ª publicação ou 'antes'}}.
    A 1ª verificação de cada dia que já encontra conteúdo novo conta como 'antes' (saiu de madrugada
    ou antes das 05:20); trocas de assinatura dentro do dia dão o horário."""
    por_fonte = defaultdict(list)
    for f, t, ok, a in linhas:
        if ok and a:
            por_fonte[f].append((dt.datetime.fromisoformat(t).astimezone(BRT), a))
    res, trocas_dia = {}, {}
    for f, obs in por_fonte.items():
        obs.sort()
        pub, trocas = {}, Counter()
        ant_ass, ant_dia = None, None
        for t, a in obs:
            dia = t.date()
            if ant_ass is not None and a != ant_ass:
                trocas[dia] += 1
                if dia not in pub:
                    pub[dia] = "antes" if dia != ant_dia else t.time()
            ant_ass, ant_dia = a, dia
        res[f], trocas_dia[f] = pub, trocas
    return res, trocas_dia


def relatorio(desde):
    conn = db.conectar()
    conn.executar(SQL_TABELA)
    linhas = conn.consultar("SELECT fonte, verificado_em, ok, assinatura FROM monitor_publicacao "
                            "WHERE verificado_em >= %s ORDER BY verificado_em", (desde.isoformat(),))
    conn.close()
    dias_obs = defaultdict(set)
    erros = Counter()
    for f, t, ok, _a in linhas:
        dias_obs[f].add(dt.datetime.fromisoformat(t).astimezone(BRT).date())
        erros[f] += not ok
    pubs, trocas = publicacoes(linhas)

    def hm(t):
        return f"{t.hour:02d}:{t.minute:02d}"

    out = ["| Local | Horário mínimo | Horário máximo | Mais comum (10 min) | Dias com publicação / dias monitorados | Obs. |",
           "|---|---|---|---|---|---|"]
    for fid in ["ES", "BA"] + [f[0] for f in FONTES]:
        p = pubs.get(fid, {})
        horas = sorted(v for v in p.values() if v != "antes")
        antes = sum(1 for v in p.values() if v == "antes")
        n_obs = len(dias_obs.get(fid, ()))
        obs = []
        if antes:
            obs.append(f"{antes} dia(s) já publicado antes das 05:20")
        if trocas.get(fid) and statistics.median(trocas[fid].values()) > 3:
            obs.append("página muda várias vezes ao dia (resultado pouco confiável)")
        if n_obs and erros[fid] > 0.5 * sum(1 for x in linhas if x[0] == fid):
            obs.append("site falhou na maioria das verificações")
        if not n_obs:
            obs.append("sem verificações")
        if horas:
            faixas = Counter(f"{t.hour:02d}:{t.minute // 10 * 10:02d}" for t in horas)
            faixa, qt = faixas.most_common(1)[0]
            h, m = map(int, faixa.split(":"))
            fim = (dt.datetime(2000, 1, 1, h, m) + dt.timedelta(minutes=10)).time()
            comum = f"{faixa}–{hm(fim)} ({qt}x)"
            out.append(f"| {NOMES[fid]} | {hm(horas[0])} | {hm(horas[-1])} | {comum} | {len(p)} / {n_obs} | {'; '.join(obs)} |")
        else:
            out.append(f"| {NOMES[fid]} | – | – | – | {len(p)} / {n_obs} | {'; '.join(obs) or 'nenhuma publicação detectada'} |")
    txt = (f"Publicação dos boletins (detectada a cada ~10 min, dias úteis 05:20–21:00, desde {desde:%d/%m/%Y})\n\n"
           + "\n".join(out))
    print(txt)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(txt + "\n")
    return txt


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--uma-vez", action="store_true")
    ap.add_argument("--relatorio", action="store_true")
    ap.add_argument("--desde", default="", help="AAAA-MM-DD (relatório)")
    a = ap.parse_args(argv)
    if a.relatorio:
        relatorio(dt.date.fromisoformat(a.desde) if a.desde else agora().date() - dt.timedelta(days=15))
    else:
        monitorar(a.uma_vez)
    return 0


if __name__ == "__main__":
    sys.exit(main())
