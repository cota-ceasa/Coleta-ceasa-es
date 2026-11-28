"""CEASA-SC (São José / Grande Florianópolis) — boletins diários em PDF no portal Joomla (DOCman).

Páginas:
  https://www.ceasa.sc.gov.br/index.php/cotacao-de-precos            -> pastas dos anos ("2026" = /2026-1)
  .../cotacao-de-precos/2026-1                                       -> pastas dos meses ("11 - Novembro")
  .../cotacao-de-precos/2026-1/11-novembro-18                        -> um PDF por dia ("16-11-2026")
  PDF: .../11-novembro-18/3734-16-11-2026/file   (a data vem do endereço do arquivo)

PDF "Relatório de Cotações do dia : 16/11/2026", Unidade São José. Colunas: Produto Variedade |
Classificação | Tipo | Origem | Embalagem | Conv. Kg | Mínimo | Comum | Máximo | Comum Kg.
Preço é por embalagem (ex.: Caixa de 20 kg); a embalagem vira 'CX 20 KG' e o app calcula o R$/kg.
Classificação às vezes quebra em 2 linhas ('Especial' / 'Escovada'): a leitura junta pela posição.
Ficam de fora itens que não são hortifrúti/grãos (carnes, bebidas, pães, queijos, carvão...).
Se o site mudar, rode:  python -m coleta.run --discover SC
"""
import datetime as dt
import io
import os
import re
from html import unescape
from urllib.parse import urljoin

from ..padronizar import cotacao, produto_detalhe, sem_acento
from .ba import ColetorBA
from .base import parse_data

URL = os.environ.get("CEASA_SC_URL", "https://www.ceasa.sc.gov.br/index.php/cotacao-de-precos")
APELIDOS = {
    "ABOBORA ABOBRINHA": "Abobrinha",
    "ABOBORA MORANGA": "Moranga",
    "BATATA INGLESA": "Batata",
    "BATATA AIPO": "Mandioquinha",
    "BATATA CARA": "Cará",
    "BANANA BRANCO": "Banana Prata",
    "BATATA IACON": "Yacon",
    "BANANA BRANCA": "Banana Prata",
    "BANANA CATURRA": "Banana Nanica",
    "COUVE FOLHA": "Couve",
    "LIMAO THAITI": "Limão Tahiti",
    "LIMA DA PERCIA": "Lima da Pérsia",
    "LARANJA BAHIA": "Laranja Baía",
    "PINHA ATEMOIA": "Pinha",
    "PITAIA": "Pitaya",
    "JABOTICABA": "Jabuticaba",
    "RADITE": "Almeirão",
    "MAMAO PAPAYA HAWAI": "Mamão Havaí",
}
# itens do boletim que não são hortifrúti/grãos (o app não acompanha)
FORA = ("BEBIDAS", "CARNES", "PAES", "QUEIJO", "MANTEIGA", "NATA", "BANHA", "CARVAO", "LICOR", "SUCO ",
        "MELADO", "POLVILHO")
EMB = {"CAIXA": "CX", "SACO": "SC", "BANDEJA": "BDJ", "FARDO": "FRD", "PACOTE": "PCT"}
NUMBR = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")
_CACHE = {}


def _norm(t):
    return re.sub(r"\s+", " ", sem_acento(unescape(t or "")).upper()).strip()


def _kg(v):
    return f"{v:g}".replace(".", ",")


def embalagem_sc(emb, conv):
    """('Caixa','20')->'CX 20 KG'; ('Unidade','1,7')->'UN 1,7 KG'; ('Maço',..)->'MOLHO'; ('Kilo','1')->'KG';
    ('Bandeja','0,3')->'BDJ 0,3 KG'; ('Dúzia',..)->'DZ'."""
    e = _norm(emb)
    try:
        peso = float((conv or "").replace(",", "."))
    except ValueError:
        peso = None
    if e in ("MACO", "MOLHO"):
        return "MOLHO"
    if e in ("KILO", "KG", "QUILO"):
        return "KG"
    if e == "DUZIA":
        return "DZ"
    if e == "UNIDADE":
        return f"UN {_kg(peso)} KG" if peso else "UN"
    if e in EMB and peso:
        return f"{EMB[e]} {_kg(peso)} KG"
    return e


def indice_anos(html):
    """Página principal -> {ano: url da pasta do ano}."""
    out = {}
    for href, ano in re.findall(r'href="([^"]*/cotacao-de-precos/((?:19|20)\d\d)(?:-\d+)?)"', html):
        out.setdefault(int(ano), urljoin(URL, unescape(href)))
    return out


def indice_meses(html, url_ano):
    """Pasta do ano -> {mês: url da pasta do mês} ('11-novembro-18' -> 11)."""
    base = re.escape(url_ano.rstrip("/").split("/cotacao-de-precos/")[-1])
    out = {}
    for href, mes in re.findall(r'href="([^"]*/cotacao-de-precos/' + base + r'/(\d{1,2})-[^"/?#]+)"', html):
        if 1 <= int(mes) <= 12:
            out.setdefault(int(mes), urljoin(URL, unescape(href)))
    return out


def documentos(html):
    """Pasta do mês -> {date: url do PDF} (data do endereço '.../3734-16-11-2026/file')."""
    out = {}
    for href, d, m, a in re.findall(r'href="([^"]*/\d+-(\d{1,2})-(\d{1,2})-(\d{4})[^"/]*/file)"', html):
        try:
            out[dt.date(int(a), int(m), int(d))] = urljoin(URL, unescape(href))
        except ValueError:
            continue
    return out


class ColetorSC(ColetorBA):
    id = "SC"
    nome = "CEASA - São José (SC)"
    uf = "SC"
    url_lista = URL

    def datas(self, page):
        hoje = dt.date.today()
        ini = getattr(self, "inicio", None) or hoje - dt.timedelta(days=30)
        if URL not in _CACHE:
            _CACHE[URL] = indice_anos(self._abrir(page, URL))
        anos = _CACHE[URL]
        if not anos:
            raise RuntimeError("nenhuma pasta de ano na página (o site mudou? rode --discover SC)")
        out = {}
        for ano in range(ini.year, hoje.year + 1):
            if ano not in anos:
                print(f"[SC] sem pasta para {ano} na página")
                continue
            meses = indice_meses(self._abrir(page, anos[ano]), anos[ano])
            for mes, url in sorted(meses.items()):
                if (ano, mes) < (ini.year, ini.month) or (ano, mes) > (hoje.year, hoje.month):
                    continue
                sep = "&" if "?" in url else "?"
                out.update(documentos(self._abrir(page, f"{url}{sep}limit=100")))
        return sorted(out.items())

    def capturar(self, page, ref):
        corpo = self._baixar(page, ref)
        if not corpo or not corpo.startswith(b"%PDF"):
            return None
        linhas = linhas_do_pdf(corpo)
        if not any(c[0] != "#DATA" for *_x, c in linhas):
            return None
        return corpo, "pdf", linhas

    def normalizar(self, linhas, data):
        data_pdf, unidade, out = None, "", []
        for _pag, _ordem, _met, cel in linhas:
            cel = list(cel)
            if cel[0] == "#DATA":
                data_pdf, unidade = parse_data(cel[1]), _norm(cel[2] if len(cel) > 2 else "")
                continue
            prod, classif, tipo, origem, emb, conv, mn, com, mx = (cel + [""] * 9)[:9]
            np_ = _norm(prod)
            if not prod or np_.startswith(FORA):
                continue
            extra = []
            if _norm(origem) == "IMPORTADO":
                extra.append("IMPORTADO")
            if _norm(tipo).startswith("ORGANIC"):
                extra.append("ORGANICO")
            desc = re.sub(r"\((?:a|o)\)", "", f"{prod} {classif} {' '.join(extra)}", flags=re.I)
            embal = embalagem_sc(emb, conv)
            if np_.startswith("OVOS") and embal == "CX 25 KG":   # caixa de ovos de 25 kg = 30 dúzias
                embal = "CX 30 DZ"
            c = cotacao(desc, embal, mn, com, mx, "", apelidos=APELIDOS,
                        data_ok=data_pdf in (None, data) and (not unidade or "SAO JOSE" in unidade))
            if c:
                out.append(c)
        vistas = {}
        for c in out:   # mesma linha repetida no boletim: a 2ª ganha " (2)"
            k = (c["produto"], c["detalhe"], c["embalagem"])
            vistas[k] = vistas.get(k, 0) + 1
            if vistas[k] > 1:
                c["detalhe"] = f"{c['detalhe']} ({vistas[k]})".strip()
        if data_pdf and data_pdf != data:
            print(f"[SC] atenção: boletim pedido para {data}, PDF diz {data_pdf} (linhas ficam 'revisar')")
        novos = sorted({c["produto"] for c in out if produto_detalhe(c["produto"], APELIDOS)[0] is None})
        if novos:
            print(f"[SC] {data}: {len(novos)} produtos novos (entram em 'Outros'): {novos[:15]}")
        rev = [f"{c['produto']} {c['detalhe']} [{c['embalagem']}]" for c in out if c["conferencia"] != "validado"]
        if rev:
            print(f"[SC] {data}: {len(out) - len(rev)} validadas; {len(rev)} para revisar: {rev[:10]}")
        return out

    def discover(self, page, pasta):
        try:
            self.inicio = dt.date.today().replace(day=1)
            ds = self.datas(page)
        finally:
            try:
                (pasta / "sc_pagina.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        print(f"boletins no mês: {len(ds)}" + (f", {ds[0][0]} a {ds[-1][0]}" if ds else ""))
        if ds:
            r = self.capturar(page, ds[-1][1])
            if r:
                (pasta / f"SC_{ds[-1][0]}.pdf").write_bytes(r[0])
                cots = self.normalizar(r[2], ds[-1][0])
                print(f"\nSC {ds[-1][0]}: {len(cots)} cotações. Primeiras:")
                for c in cots[:8]:
                    print("   ", c)


def linhas_do_pdf(dados):
    """PDF -> [(pagina, ordem, 'pdf', celulas)].
    1ª linha: ['#DATA', 'dd/mm/aaaa', 'São José'].
    Linhas de preço: [produto, classificação, tipo, origem, embalagem, conv_kg, mín, comum, máx]."""
    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        for npag, pg in enumerate(pdf.pages, 1):
            ws = pg.extract_words()
            if npag == 1:
                t = pg.extract_text() or ""
                d = re.search(r"Cota[cç][oõ]es do dia\s*:\s*(\d{2}/\d{2}/\d{4})", t) or \
                    re.search(r"(\d{2}/\d{2}/\d{4})", t)
                u = re.search(r"Unidade\s*:\s*\n?\s*([^\n]+)", t)
                out.append((1, 0, "pdf", ["#DATA", d.group(1) if d else "", u.group(1).strip() if u else ""]))
            cab = {}
            for w in ws:
                if w["top"] < 140:
                    cab.setdefault(_norm(w["text"]), w)
            if "CLASSIFICACAO" not in cab or "MINIMO" not in cab:
                continue
            fim_cab = max(w["bottom"] for k, w in cab.items() if k in ("MINIMO", "KG", "MAXIMO"))
            xc = cab["CLASSIFICACAO"]["x0"] - 12
            xt = cab.get("TIPO", {"x0": 243})["x0"] - 12
            xo = cab.get("ORIGEM", {"x0": 286})["x0"] - 6
            xe = cab.get("EMBALAGEM", {"x0": 332})["x0"] - 8
            xk = cab.get("CONV.", {"x0": 391})["x0"] - 8
            xn = cab["MINIMO"]["x0"] - 15
            xck = cab.get("MAXIMO", {"x1": 531})["x1"] + 8   # depois do Máximo: 'Comum Kg' (ignorado)
            rodape = min((w["top"] for w in ws if _norm(w["text"]).startswith("TERADYNE")
                          or "BR-101" in w["text"] or "@CEASA" in _norm(w["text"])), default=pg.height)
            corpo = [w for w in ws if fim_cab + 2 < w["top"] < rodape - 25]
            ancoras = []   # linhas de preço: 3 números no formato brasileiro entre Mínimo e Máximo
            for w in sorted(corpo, key=lambda w: w["top"]):
                if xn <= w["x0"] < xck and NUMBR.match(w["text"]):
                    if not ancoras or abs(w["top"] - ancoras[-1]) > 6:
                        ancoras.append(w["top"])
            grupos = {a: [] for a in ancoras}
            for w in corpo:
                perto = min(ancoras, key=lambda a: abs(a - w["top"]), default=None)
                if perto is not None and abs(perto - w["top"]) <= 11:
                    grupos[perto].append(w)
            for a in ancoras:
                g = sorted(grupos[a], key=lambda w: (round(w["top"]), w["x0"]))

                def col(x0, x1):
                    return " ".join(w["text"] for w in g if x0 <= w["x0"] < x1)
                nums = [w["text"] for w in sorted(g, key=lambda w: w["x0"])
                        if xn <= w["x0"] < xck and NUMBR.match(w["text"])]
                if len(nums) < 3 or not col(0, xc):
                    continue
                out.append((npag, len(out), "pdf", [col(0, xc), col(xc, xt), col(xt, xo), col(xo, xe),
                                                    col(xe, xk), col(xk, xn), nums[0], nums[1], nums[2]]))
    return out
