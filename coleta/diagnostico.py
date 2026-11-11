"""Diagnóstico de acesso: o GitHub consegue abrir os sites das CEASAs? Como computador ou como Android?

Uso: python -m coleta.run --diagnostico
Gera saida/diagnostico.txt (resumo) + capturas de tela e HTML de cada tentativa.
"""
import socket
import time
import urllib.request
from urllib.parse import urlparse

from .ceasas.mg import URL_MG

ALVOS = [
    ("MG formulário (mobile)", URL_MG),
    ("MG site institucional", "https://www.ceasaminas.com.br/informacoesmercado/contator_boletimdiarioprecos.asp"),
    ("ES formulário (controle)", "http://200.198.51.71/detec/filtro_boletim_es/filtro_boletim_es.php"),
]
PERFIS = ["computador", "android"]


def _ip_publico():
    for u in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            return urllib.request.urlopen(u, timeout=10).read().decode().strip()
        except Exception:  # noqa: BLE001
            pass
    return "?"


def _rede(url):
    h = urlparse(url)
    host, porta = h.hostname, h.port or (443 if h.scheme == "https" else 80)
    try:
        ip = socket.gethostbyname(host)
    except Exception as e:  # noqa: BLE001
        return f"DNS falhou ({e})"
    try:
        socket.create_connection((ip, porta), timeout=15).close()
        return f"DNS ok ({ip}), conexão TCP na porta {porta} ok"
    except Exception as e:  # noqa: BLE001
        return f"DNS ok ({ip}), conexão TCP na porta {porta} FALHOU ({e})"


def rodar(p, saida):
    linhas = [f"IP público do GitHub: {_ip_publico()}", ""]
    for nome, url in ALVOS:
        linhas += [f"=== {nome} ===", url, "rede: " + _rede(url)]
        for perfil in PERFIS:
            kw = dict(p.devices["Pixel 7"]) if perfil == "android" else {}
            browser = p.chromium.launch()
            ctx = browser.new_context(ignore_https_errors=True, locale="pt-BR", **kw)
            page = ctx.new_page()
            tag = f"{nome.split()[0]}_{nome.split()[1] if len(nome.split()) > 1 else ''}_{perfil}".replace("(", "").replace(")", "")
            t0 = time.time()
            try:
                r = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                corpo = page.inner_text("body")[:300].replace("\n", " ") if page.query_selector("body") else ""
                selects = page.eval_on_selector_all("select", "e => e.map(x => x.id || x.name)")
                botoes = page.eval_on_selector_all("input[type=button],button,input[type=submit]", "e => e.map(x => x.id || x.value || x.textContent).slice(0, 8)")
                linhas.append(f"  [{perfil}] HTTP {r.status if r else '?'} em {time.time() - t0:.1f}s | título: {page.title()!r}")
                linhas.append(f"      selects: {selects} | botões: {botoes}")
                linhas.append(f"      texto: {corpo}")
                page.screenshot(path=str(saida / f"diag_{tag}.png"))
                (saida / f"diag_{tag}.html").write_text(page.content(), encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                linhas.append(f"  [{perfil}] FALHOU em {time.time() - t0:.1f}s: {str(e).splitlines()[0][:200]}")
            ctx.close()
            browser.close()
        linhas.append("")
    txt = "\n".join(linhas)
    (saida / "diagnostico.txt").write_text(txt, encoding="utf-8")
    print(txt, flush=True)
