"""CEASA-RS (Porto Alegre) — boletins diários em PDF guardados em pastas do Google Drive.

Página de cotações (portal do governo do RS):
  https://www.ceasa.rs.gov.br/cotacoes-de-precos
Estrutura: um painel por ano ("2026") com um link por mês ("NOVEMBRO") para uma pasta pública do
Google Drive. Dentro da pasta, um PDF por dia: "Cotacao 16/11/2026.pdf" (a data vem do nome).
A pasta é listada pela visão embutida do Drive (embeddedfolderview, HTML simples); se ela falhar,
pela página normal da pasta. O PDF é baixado pelo link público de download.

PDF: cabeçalho "Data: 16/11/2026  Hora: 10:52" e "Unidade: CEASA/RS - PORTO ALEGRE"; colunas
Produto | UND | MAX | MAIS FREQUENTE | MÍNIMO (atenção: o máximo vem ANTES do mínimo), preços no
formato "R$ 4.00" (ponto decimal). Seções: VERDURAS E LEGUMES, FRUTAS, CENTRAL DE FLORES, CARNES,
PESCADOS E FRUTOS DO MAR, DIVERSOS. Flores e carnes ficam de fora; preço 0,00 = produto sem oferta.
Se o site mudar, rode:  python -m coleta.run --discover RS
"""
import datetime as dt
import io
import os
import re
from html import unescape
from urllib.parse import urlencode

from ..padronizar import cotacao, produto_detalhe, sem_acento
from .ba import ColetorBA
from .base import parse_data

URL = os.environ.get("CEASA_RS_URL", "https://www.ceasa.rs.gov.br/cotacoes-de-precos")
MESES = {m: i for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO",
                                     "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], 1)}
# Pastas conhecidas (página de 05/11/2026). Usadas só se a página da CEASA-RS não abrir; meses novos
# vêm sempre da página.
PASTAS_CONHECIDAS = {
    (2026, 1): "11rUjgzDqn89DVZrhPdWcP02LP9Ja4EoK", (2026, 2): "1WMryDfV3gbj7zRk3jP1mDtl-vIE9vAHb",
    (2026, 3): "1rFc6Z9rOw5xVa4OjfVw--0-UzzsB8TzM", (2026, 4): "1b6asTJ_sXoARJTuTF4tSK2UMdQkE91Wo",
    (2026, 5): "16v6bWKgFIvjeM1p_xZHDXOKmiUhxaEh0", (2026, 6): "18RTfDm-OdK20nLiKtfGewehBQOHzGnI5",
    (2026, 7): "1TVaSs06V-NqYy9ZRh3c4TpM6dWSSV8jv", (2026, 8): "1IrZZFzbjU1BiOTHKg1tEO4wXG6WRs8t3",
    (2026, 9): "1l6U96VcWQlLthmcHyAAyhc4CYS1OgY0n", (2026, 10): "18lqVzFcmSVyUCLTtHiY9rGJSxdEao210",
    (2026, 11): "1dEPfz7Rxnf4mC8ysKhufxGDX5Tr2xTq-",
    (2025, 1): "10SWzeoDawGWprypRLhLMUVd97s-Kf17I", (2025, 2): "1W_yLS8pgfBhB_TgjG1L-RO0AE6RuyC0G",
    (2025, 3): "1VloQjTaLYRI2D3Je5_Of3KZ1PaU3W9Jb", (2025, 4): "1yoQhm2ovgXxpK0vvr4aST7bhnWK4BEJD",
    (2025, 5): "1aNMcZfkufEg5VhoK4FtvMHOSqxsZGgB4", (2025, 6): "1G4Uc7KEHffebxarUKKBWu1rP2bxdzBhT",
    (2025, 7): "19ihcDWqUxxDiSvPGD3xm29D_dMmWbv4l", (2025, 8): "1YHJzMbNX1S3gAYhkm9ahIal02fW3H-1G",
    (2025, 9): "16XIpMqDfVo7c8ObcvFj-3eemnXwbjEpB", (2025, 10): "1y0WWByRyj6dGTbKvvFXpBBv9GV9NY9Db",
    (2025, 11): "14ZKhUPV6rt20_QizGn5Tw7D7_4lyEd3j", (2025, 12): "1H7amJHE6-sysxqZYLjEq9bArQ0K_EvxY",
    (2024, 1): "1O0S6NSlJdRapBfSgmH6shanNvF0otmRy", (2024, 2): "1-7SzKCliuEFPdUnU1rUUs60aSEPGerPl",
    (2024, 3): "1B0BuECbQk9hqLPTx88wz4zBosQEleUTY", (2024, 4): "1-cnE1fsbcs9eh6HdqhWuCM-K7FW0ys57",
    (2024, 5): "1KtB5BfNbOReatrkGDjSE2hKZPqNohMiJ", (2024, 6): "1Wjf1BF3X0zfSS4r90p6NjYTGvQCUHFZE",
    (2024, 7): "1zOMnbj07NBK7eJ148L3mCQYnQhzJEAYX", (2024, 8): "1RD3XbL3KCrFqq5ARyxbGy9ljoreeKBCr",
    (2024, 9): "1RUkEp5CD-AbTJFd_vIdM_ndJL9LkOZWq", (2024, 10): "1886ZIYZvIR_2fnZ4u7p0KWZQeC8LXfYX",
    (2024, 11): "10bIz7G0CCQthHV33TUtZGqwi40BBiwJV", (2024, 12): "1xvf3shX6NB8Q4iDP6IDkZE7Noekmf09Q",
}
APELIDOS = {
    "AIPO SALSAO": "Salsão",
    "RADITE ALMEIRAO": "Almeirão",
    "RADITE": "Almeirão",
    "TEMPERO VERDE": "Cheiro Verde",
    "BANANA CATURRA NANICA": "Banana Nanica",
    "BANANA CATURRA": "Banana Nanica",
    "BANANA TERRAS E OUTRAS": "Banana Terra",
    "FRUTA DO CONDE PINHA": "Pinha",
    "FRUTA DO CONDE": "Pinha",
    "KINKAN": "Laranja Kinkan",
    "LARANJA UMBIGO BAHIA": "Laranja Baía",
    "LARANJA UMBIGO": "Laranja Baía",
    "LIMA": "Lima da Pérsia",
    "LIMAO TAITI": "Limão Tahiti",
    "MAMAO AMAZONAS PAPAIA": "Mamão Havaí",
    "MAMAO AMAZONAS": "Mamão Havaí",
    "PESSEGO": "Pêssego",
    "OVO": "Ovos",
    "CACAO FILE": "Cação",            # 'Filé de Cação' (sem isto casaria com 'Cacau')
    "CACAO": "Cação",
    "LOMBO DE BACALHAU": "Bacalhau",
}
SECOES_FORA = ("CENTRAL DE FLORES", "FLORES", "CARNES")
PRECO = re.compile(r"^\d{1,3}(?:[.,]\d{3})*[.,]\d{2}$|^\d+[.,]\d{2}$")
_CACHE = {}   # índice da página (ano, mês) -> id da pasta


def _norm(t):
    return re.sub(r"\s+", " ", sem_acento(unescape(t or "")).upper()).strip()


def numero_rs(txt):
    """'4.00' / '1,234.56' / '1.234,56' / '4,00' -> texto no padrão '1234,56' de padronizar.numero."""
    t = (txt or "").replace("R$", "").strip()
    if not t:
        return ""
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return f"{float(t):.2f}".replace(".", ",")
    except ValueError:
        return ""


def embalagem_rs(und, produto):
    """UND do boletim -> embalagem padrão. 'KG'->'KG'; 'DZ'->'DZ'; 'UND'->'UN'; 'MOL'->'MOLHO';
    'BDJ' de 'Milho Verde(3UN)'->'BDJ 3 UNID'; 'CX 30B/30U' de 'Ovo Branco CX30DZ'->'CX 30 DZ'."""
    u = _norm(und)
    p = _norm(produto)
    dz = re.search(r"CX\s*(\d+)\s*DZ", p)
    un = re.search(r"\(?(\d+)\s*UN\)?", p)
    if dz and u.startswith("CX"):
        return f"CX {dz.group(1)} DZ"
    if u in ("KG", "DZ"):
        return u
    if u in ("UND", "UN", "UNID"):
        return "UN"
    if u in ("MOL", "MC", "MOLHO"):
        return "MOLHO"
    if u in ("BDJ", "CX", "PCT") and un:
        return f"{u} {un.group(1)} UNID"
    return u


def _limpa_produto(p):
    """Tira do nome o que é embalagem: 'Ovo Branco CX30DZ' -> 'Ovo Branco'; 'Milho Verde(3UN)' -> 'Milho Verde'."""
    p = re.sub(r"\bCX\s*\d+\s*DZ\b|\bCXT\b|\(?\b\d+\s*UN\b\)?", " ", p, flags=re.I)
    p = re.sub(r"^\s*Fil[ée]\s+(?:de\s+)?(.+)$", r"\1 Filé", p, flags=re.I)   # 'Filé de Tilápia' -> 'Tilápia Filé'
    return re.sub(r"\s+", " ", p).strip()


def indice(html):
    """Página de cotações -> {(ano, mês): id da pasta do Drive}."""
    out, ano = {}, None
    tok = re.compile(r'<h4[^>]*>.*?>\s*(20\d\d)\s*<.*?</h4>'
                     r'|<a\b[^>]*href="([^"]*drive\.google\.com/[^"]*folders/([\w-]+)[^"]*)"[^>]*>(.*?)</a>',
                     re.S | re.I)
    for m in tok.finditer(html):
        if m.group(1):
            ano = int(m.group(1))
            continue
        mes = MESES.get(_norm(re.sub(r"<[^>]+>|&nbsp;", " ", m.group(4))))
        if ano and mes:
            out[(ano, mes)] = m.group(3)
    return out


class ColetorRS(ColetorBA):
    id = "RS"
    nome = "CEASA - Porto Alegre (RS)"
    uf = "RS"
    url_lista = URL

    def _pastas(self, page):
        if URL not in _CACHE:
            try:
                idx = indice(self._abrir(page, URL))
                if not idx:
                    raise RuntimeError("nenhuma pasta de mês na página (o site mudou? rode --discover RS)")
            except Exception as e:  # noqa: BLE001
                print(f"[RS] página de cotações não abriu ({str(e).splitlines()[0]}); usando as pastas conhecidas")
                idx = {}
            _CACHE[URL] = {**PASTAS_CONHECIDAS, **idx}
        return _CACHE[URL]

    def _listar_pasta(self, page, pasta):
        """[(id do arquivo, nome)] da pasta pública do Drive."""
        itens = []
        try:
            r = page.request.get(f"https://drive.google.com/embeddedfolderview?id={pasta}", timeout=60000)
            if r.ok:
                html = r.text()
                itens = re.findall(r'id="entry-([\w-]+)".*?class="flip-entry-title"[^>]*>(.*?)</div>', html, re.S)
        except Exception as e:  # noqa: BLE001
            print(f"[RS] visão embutida da pasta {pasta} falhou ({str(e).splitlines()[0]}); tentando a página da pasta")
        if not itens:   # alternativa: página normal da pasta (precisa de JavaScript)
            page.goto(f"https://drive.google.com/drive/folders/{pasta}", wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_selector("[data-id]", timeout=30000)
            except Exception:  # noqa: BLE001 (pasta vazia)
                return []
            page.wait_for_timeout(1500)
            itens = page.evaluate("""() => {
                const out = {};
                for (const e of document.querySelectorAll('[data-id]')) {
                    const id = e.getAttribute('data-id');
                    const t = (e.getAttribute('aria-label') || e.innerText || '').split('\\n')[0].trim();
                    if (id && t && !out[id]) out[id] = t;
                }
                return Object.entries(out);
            }""")
        return [(i, unescape(re.sub(r"<[^>]+>", "", n)).strip()) for i, n in itens]

    def datas(self, page):
        hoje = dt.date.today()
        ini = getattr(self, "inicio", None) or hoje - dt.timedelta(days=30)
        pastas = self._pastas(page)
        out, sem_data = {}, []
        for (ano, mes), pasta in sorted(pastas.items()):
            if (ano, mes) < (ini.year, ini.month) or (ano, mes) > (hoje.year, hoje.month):
                continue
            for fid, nome in self._listar_pasta(page, pasta):
                if not nome.lower().endswith(".pdf"):
                    continue
                m = re.search(r"(\d{1,2})[/_.\-](\d{1,2})[/_.\-](\d{4}|\d{2})", nome)
                try:
                    d = dt.date(int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0),
                                int(m.group(2)), int(m.group(1))) if m else None
                except ValueError:
                    d = None
                if d is None:
                    sem_data.append(nome)
                    continue
                out[d] = fid   # nome repetido: vale o último da lista
        if sem_data:
            print(f"[RS] {len(sem_data)} arquivo(s) sem data no nome, ignorados: {sem_data[:5]}")
        if not out and not pastas:
            raise RuntimeError("nenhuma pasta de boletins encontrada (o site mudou? rode --discover RS)")
        return sorted(out.items())

    def _baixar_drive(self, page, fid):
        """Bytes do PDF público do Drive; None se o arquivo não existir."""
        urls = [f"https://drive.usercontent.google.com/download?id={fid}&export=download",
                f"https://drive.google.com/uc?export=download&id={fid}"]
        ultimo = None
        for url in urls:
            r = page.request.get(url, timeout=90000)
            if r.status == 404:
                continue
            if not r.ok:
                ultimo = f"HTTP {r.status}"
                continue
            corpo = r.body()
            if corpo.startswith(b"%PDF"):
                return corpo
            html = corpo.decode("utf-8", "replace")   # aviso "não foi possível verificar vírus": confirma
            acao = re.search(r'<form[^>]+action="([^"]+)"', html)
            if acao:
                campos = dict(re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', html))
                r2 = page.request.get(unescape(acao.group(1)) + "?" + urlencode(campos), timeout=90000)
                if r2.ok and r2.body().startswith(b"%PDF"):
                    return r2.body()
            ultimo = "resposta não é PDF"
        if ultimo:
            raise RuntimeError(f"download do Drive falhou ({ultimo}) para o arquivo {fid}")
        return None

    def capturar(self, page, ref):
        corpo = self._baixar_drive(page, ref)
        if not corpo:
            return None
        linhas = linhas_do_pdf(corpo)
        if not any(c[0] != "#DATA" for *_x, c in linhas):
            return None
        return corpo, "pdf", linhas

    def normalizar(self, linhas, data):
        data_pdf, out = None, []
        for _pag, _ordem, _met, cel in linhas:
            cel = list(cel)
            if cel[0] == "#DATA":
                data_pdf = parse_data(cel[1])
                continue
            secao, prod, und, mx, com, mn = (cel + [""] * 6)[:6]
            if _norm(secao).startswith(SECOES_FORA) or not prod:
                continue
            mx, com, mn = numero_rs(mx), numero_rs(com), numero_rs(mn)
            if com in ("", "0,00"):   # 0,00 = produto sem oferta no dia
                continue
            c = cotacao(_limpa_produto(prod), embalagem_rs(und, prod), mn, com, mx, "",
                        apelidos=APELIDOS, data_ok=data_pdf in (None, data))
            if c:
                out.append(c)
        vistas = {}
        for c in out:   # mesma linha repetida no boletim: a 2ª ganha " (2)"
            k = (c["produto"], c["detalhe"], c["embalagem"])
            vistas[k] = vistas.get(k, 0) + 1
            if vistas[k] > 1:
                c["detalhe"] = f"{c['detalhe']} ({vistas[k]})".strip()
        if data_pdf and data_pdf != data:
            print(f"[RS] atenção: boletim pedido para {data}, PDF diz {data_pdf} (linhas ficam 'revisar')")
        novos = sorted({c["produto"] for c in out if produto_detalhe(c["produto"], APELIDOS)[0] is None})
        if novos:
            print(f"[RS] {data}: {len(novos)} produtos novos (entram em 'Outros'): {novos[:15]}")
        rev = [f"{c['produto']} {c['detalhe']} [{c['embalagem']}]" for c in out if c["conferencia"] != "validado"]
        if rev:
            print(f"[RS] {data}: {len(out) - len(rev)} validadas; {len(rev)} para revisar: {rev[:10]}")
        return out

    def discover(self, page, pasta):
        try:
            idx = self._pastas(page)
        finally:
            try:
                (pasta / "rs_pagina.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        print(f"pastas de meses: {len(idx)}" + (f", de {min(idx)} a {max(idx)}" if idx else ""))
        self.inicio = dt.date.today().replace(day=1)
        ds = self.datas(page)
        print(f"boletins no mês: {len(ds)}" + (f", {ds[0][0]} a {ds[-1][0]}" if ds else ""))
        if ds:
            r = self.capturar(page, ds[-1][1])
            if r:
                (pasta / f"RS_{ds[-1][0]}.pdf").write_bytes(r[0])
                cots = self.normalizar(r[2], ds[-1][0])
                print(f"\nRS {ds[-1][0]}: {len(cots)} cotações. Primeiras:")
                for c in cots[:8]:
                    print("   ", c)


def linhas_do_pdf(dados):
    """PDF -> [(pagina, ordem, 'pdf', celulas)].
    1ª linha: ['#DATA', 'dd/mm/aaaa', 'CEASA/RS - PORTO ALEGRE'].
    Linhas de preço: [seção, produto, und, máx, mais frequente, mín] (ordem do boletim)."""
    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        secao = ""
        xu, xp = 230, 330   # início das colunas UND e preços (ajustado pelo cabeçalho quando existe)
        for npag, pg in enumerate(pdf.pages, 1):
            ws = pg.extract_words(keep_blank_chars=False)
            if npag == 1:
                t = pg.extract_text() or ""
                d = re.search(r"Data:\s*(\d{2}/\d{2}/\d{4})", t)
                u = re.search(r"Unidade:\s*(.+)", t)
                out.append((1, 0, "pdf", ["#DATA", d.group(1) if d else "", u.group(1).strip() if u else ""]))
            cab = {_norm(w["text"]): w for w in ws if w["top"] < 120}
            if "UND" in cab and "MAX" in cab:
                xu = cab["UND"]["x0"] - 15
                xp = cab["MAX"]["x0"] - 25
            rows = {}
            for w in ws:
                rows.setdefault(round(w["top"]), []).append(w)
            for top in sorted(rows):
                r = sorted(rows[top], key=lambda w: w["x0"])
                txt = " ".join(w["text"] for w in r)
                nt = _norm(txt)
                if nt.startswith(("BOLETIM", "DATA:", "UNIDADE:", "PRODUTO UND", "PAGINA")):
                    continue
                precos = [w["text"] for w in r if w["x0"] >= xp and PRECO.match(w["text"])]
                if len(precos) < 3:
                    if r[-1]["x0"] < xu and txt == txt.upper() and re.search(r"[A-Z]", nt):
                        secao = txt   # título de seção (linha só com maiúsculas, sem preços)
                    continue
                prod = " ".join(w["text"] for w in r if w["x1"] <= xu + 10)
                und = " ".join(w["text"] for w in r if w["x1"] > xu + 10 and w["x0"] < xp and w["text"] != "R$")
                out.append((npag, len(out), "pdf", [secao, prod, und, precos[0], precos[1], precos[2]]))
    return out
