"""CEASA-RJ (Irajá) — boletins em PDF publicados no portal rj.gov.br/ceasa.

Navegação (portal Drupal, o mesmo tipo do da BA; usa o mesmo acesso "navegador comum"):
  Cotação  https://www.rj.gov.br/ceasa/Cota%C3%A7%C3%A3o   -> links "2026", "2025"
  Ano      .../ceasa/node/600                               -> links "Novembro", "Outubro"...
  Mês      .../ceasa/node/661                               -> links "16 de novembro" -> PDF
A data vem do nome do arquivo ("Boletim diário de preços  16 11 2026 (1).pdf") ou, se não der,
do texto do link + ano. O PDF traz a data no cabeçalho, usada para conferir.

Colunas do PDF (gerado no Excel; a posição muda a cada página, então é lida do cabeçalho):
  PRODUTOS | TIPO | UNIDADE EMBALAGEM | VARIAÇÃO 12 MESES | MIN | MODAL | MAX
Linhas "S/C" (sem cotação) não têm preço e são ignoradas.
Se o site mudar, rode:  python -m coleta.run --discover RJ
"""
import os
import re
from html import unescape
from urllib.parse import unquote, urljoin

import datetime as dt

from ..padronizar import cotacao, produto_detalhe, sem_acento
from .ba import NUM, ColetorBA, _linhas_de_palavras
from .base import parse_data

URL = os.environ.get("CEASA_RJ_URL", "https://www.rj.gov.br/ceasa/Cota%C3%A7%C3%A3o")
MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
     "setembro", "outubro", "novembro", "dezembro"], 1)}
APELIDOS = {
    "OVO": "Ovos",
    "BANANA DA TERRA": "Banana Terra",
    "LISCHIA": "Lichia",
    "SAPUTI": "Sapoti",
    "BANANA NANICA D AGUA": "Banana Nanica",
    "BANANA NANICA D’AGUA": "Banana Nanica",
    "FRUTA DE CONDE PINHA": "Pinha",
    "JABOTICABA": "Jabuticaba",
    "LARANJA BAHIA": "Laranja Baía",
    "LIMAO TAITI": "Limão Tahiti",
    "MAMAO PAPAYA HAVAI": "Mamão Havaí",
    "MARACUJA": "Maracujá Azedo",
    "UVA ROSADA NIAGARA": "Uva Niágara",
    "AIPO SALSAO": "Salsão",
    "ERVA DOCE FUNCHO": "Erva Doce",
}
UNID = re.compile(r"^(cx|sc|unid|un|preg|ama|mol|pct|kg|\d+,?\d*kg)$", re.I)


class ColetorRJ(ColetorBA):
    id = "RJ"
    nome = "CEASA - Rio de Janeiro (RJ)"
    uf = "RJ"
    url_lista = URL

    def datas(self, page):
        out = {}
        anos = _links(self._abrir(page), URL, lambda t: re.fullmatch(r"20\d{2}", t))
        if not anos:
            raise RuntimeError("nenhum ano na página de cotação (o site mudou? rode --discover RJ)")
        ini = getattr(self, "inicio", None)  # definido por run.py: não visita meses anteriores
        for ano_txt, url_ano in anos:
            if ini and int(ano_txt) < ini.year:
                continue
            meses = _links(self._abrir(page, url_ano), url_ano, lambda t: _mes(t))
            for mes_txt, url_mes in meses:
                if ini and (int(ano_txt), _mes(mes_txt)) < (ini.year, ini.month):
                    continue
                page.wait_for_timeout(500)  # pausa educada entre páginas
                html = self._abrir(page, url_mes)
                for txt, url in _links(html, url_mes, lambda t: True):
                    if not re.search(r"\.pdf$", url, re.I):
                        continue
                    d = data_do_arquivo(url) or _data_texto(txt, int(ano_txt), _mes(mes_txt))
                    if d and d not in out:
                        out[d] = url
        return sorted(out.items())

    def capturar(self, page, ref):
        corpo = self._baixar(page, ref)
        if corpo is None or not corpo.startswith(b"%PDF"):
            return None
        linhas = linhas_do_pdf(corpo)
        if not any(len(c) == 7 for *_x, c in linhas):
            return None
        return corpo, "pdf", linhas

    def normalizar(self, linhas, data):
        data_pdf = None
        out = []
        for _pag, _ordem, _metodo, cel in linhas:
            if len(cel) == 1:
                data_pdf = data_pdf or parse_data(cel[0])
                continue
            prod, tipo, unid, _var, mn, com, mx = cel
            c = cotacao(f"{prod} {tipo}", embalagem_rj(unid), mn, com, mx, "",
                        apelidos=APELIDOS, data_ok=data_pdf in (None, data))
            if c:
                out.append(c)
        vistas = {}
        for c in out:  # mesma linha repetida (ex.: MANGA TOMMY em Cx 18 e Cx 5 têm embalagens diferentes)
            k = (c["produto"], c["detalhe"], c["embalagem"])
            vistas[k] = vistas.get(k, 0) + 1
            if vistas[k] > 1:
                c["detalhe"] = f"{c['detalhe']} ({vistas[k]})".strip()
        novos = sorted({c["produto"] for c in out if produto_detalhe(c["produto"], APELIDOS)[0] is None})
        if novos:
            print(f"[RJ] {data}: produtos novos (entram em 'Outros'; cadastre em GRUPOS): {novos}")
        if data_pdf and data_pdf != data:
            print(f"[RJ] atenção: boletim pedido para {data}, PDF diz {data_pdf} (linhas ficam 'revisar')")
        revisar = sorted({f"{c['produto']} {c['detalhe']} [{c['embalagem']}]".strip()
                          for c in out if c["conferencia"] != "validado"})
        if revisar:
            print(f"[RJ] {data}: {len(out) - len(revisar)} validadas; {len(revisar)} fora do app: "
                  f"{revisar[:10]}{' ...' if len(revisar) > 10 else ''}")
        return out

    def discover(self, page, pasta):
        try:
            html = self._abrir(page)
        finally:
            (pasta / "pagina_inicial.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
        print("anos:", _links(html, URL, lambda t: re.fullmatch(r"20\d{2}", t)))
        datas = self.datas(page)
        print(f"{len(datas)} boletins. Mais antigos/mais novos:", datas[:3], "...", datas[-3:])


def _links(html, base, filtro):
    """[(texto, url)] dos links do portal cujo texto passa no filtro, sem repetir URL."""
    out, vistas = [], set()
    for href, texto in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        texto = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", texto))).strip()
        url = urljoin(base, unescape(href))
        if "/ceasa/" not in url or url in vistas or not filtro(texto):
            continue
        vistas.add(url)
        out.append((texto, url))
    return out


def _mes(t):
    return MESES.get(sem_acento(t).lower().strip())


def _data_texto(txt, ano, mes):
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)", sem_acento(txt).lower())
    if not m:
        return None
    try:
        return dt.date(ano, MESES.get(m.group(2), mes or 0), int(m.group(1)))
    except ValueError:
        return None


def data_do_arquivo(url):
    """'Boletim diário de preços  16 11 2026 (1).pdf' / '..._0.pdf' -> date."""
    nome = unquote(url.rsplit("/", 1)[-1])
    m = re.search(r"(\d{1,2})[\s._-]+(\d{1,2})[\s._-]+(20\d{2})", nome)
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    try:
        return dt.date(y, mth, d)
    except ValueError:
        return None


def linhas_do_pdf(dados):
    """PDF -> [(pagina, ordem, 'pdf', celulas)].
    Preço: 7 células [produto, tipo, unidade, variação, mín, modal, máx]; data do cabeçalho: 1 célula."""
    import io

    import pdfplumber

    out, col = [], None
    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        for npag, pag in enumerate(pdf.pages, 1):
            ws = pag.extract_words()
            col = _colunas(ws) or col
            if col is None:
                continue
            for linha in _linhas_de_palavras(ws):
                texto = " ".join(w["text"] for w in linha)
                if "Dia Semana" in texto or re.search(r"Dia\s+Semana", texto):
                    m = re.search(r"\d{2}/\d{2}/\d{4}", texto)
                    if m:
                        out.append((npag, len(out), "pdf", [m.group(0)]))
                    continue
                if linha[0]["top"] <= col["topo"]:
                    continue
                cel = _celulas(linha, col)
                if cel:
                    out.append((npag, len(out), "pdf", cel))
    return out


def _colunas(ws):
    """Posições do cabeçalho da página (x de TIPO, UNIDADE, VARIAÇÃO e a linha do cabeçalho)."""
    h = {}
    for w in ws:
        t = sem_acento(w["text"]).upper()
        if t in ("TIPO", "UNIDADE", "VARIACAO", "MIN") and t not in h:
            h[t] = w
    if len(h) < 4:
        return None
    return {"tipo": h["TIPO"]["x0"] - 14, "unid": h["UNIDADE"]["x0"] - 6,
            "var": h["VARIACAO"]["x0"] - 8, "topo": h["MIN"]["top"] + 12}


def _celulas(ws, col):
    ws = list(ws)
    nums = []
    while ws and len(nums) < 3 and NUM.match(ws[-1]["text"]):
        nums.insert(0, ws.pop()["text"])
    if len(nums) != 3:
        return None  # sem cotação (S/C), seção ou cabeçalho
    var = []
    while ws and ws[-1]["x0"] >= col["var"]:
        var.insert(0, ws.pop()["text"])
    prod = [w for w in ws if w["x0"] < col["tipo"]]
    resto = [w for w in ws if w["x0"] >= col["tipo"]]
    i = next((k for k, w in enumerate(resto) if w["x0"] >= col["unid"] or UNID.match(w["text"])), len(resto))
    txt = lambda p: " ".join(w["text"] for w in p)
    if not prod:
        return None
    return [txt(prod), txt(resto[:i]), txt(resto[i:]), " ".join(var), *nums]


def embalagem_rj(u):
    """Unidade do boletim do RJ -> forma padrão de emb_info.
    'Cx 20 kg'->'CX 20 KG'; 'Cx 1 kg / 4 band 0,25 kg'->'CX 1 KG'; 'Preg 20 kg/8 cab'->'CX 20 KG';
    'Unid 2,5 kg'->'UN 2,5 KG'; 'Ama 0,25 kg'->'UN 0,25 KG' (maço); 'Ama 4,5 kg'->'CX 4,5 KG';
    'Cx 30 dz'->'CX 30 DZ'; 'kg'->'KG'; 'Unid'->'UN'."""
    e = sem_acento(u or "").upper().strip()
    e = re.split(r"\s*/\s*|\s+-\s+", e)[0]
    e = re.sub(r"(\d)(KG|DZ)\b", r"\1 \2", e)
    e = re.sub(r"\s+", " ", e).strip()
    if e in ("UNID", "UN", "UND"):
        return "UN"
    m = re.fullmatch(r"(CX|SC|PREG|AMA|MOL|PCT|UNID|UN)?\s*([\d,]+)\s*(KG|DZ)", e)
    if not m:
        return e
    emb, num, un = m.groups()
    if un == "DZ":
        return f"CX {num} DZ"
    peso = float(num.replace(",", "."))
    if emb in (None, "UNID", "UN") or (emb in ("AMA", "MOL", "PCT") and peso < 2):
        return f"UN {num} KG"   # preço por unidade/maço
    return f"{'SC' if emb == 'SC' else 'CX'} {num} KG"   # preço da embalagem -> R$/kg
