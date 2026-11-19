"""CEASA-BA (Salvador) — boletins em PDF publicados pela SDE no portal ba.gov.br.

Página com a lista de boletins (um link por dia, mais novo primeiro):
  https://www.ba.gov.br/sde/boletim-informativo-ceasa-periodo-eleitoral
Cada link aponta para um PDF (…/files/2026-11/13-11-2026.pdf) ou, às vezes, para uma página de
publicação que contém o PDF. A data vem do NOME DO ARQUIVO (o texto do link tem erros de digitação,
ex.: "02/09/2026" apontando para 02-10-2026.pdf); se o arquivo não tiver data, usa o texto.
O PDF traz "EMISSÃO: dd/mm/aaaa", usado para conferir o dia (diferente = linhas ficam 'revisar').

Colunas do PDF: PRODUTO | UNIDADE | PROCEDÊNCIA | MÍNIMO | MAIS COMUM | MÁXIMO | SITUAÇÃO (EST/FIR/FRA).
Se a página mudar de endereço, defina CEASA_BA_URL ou rode:  python -m coleta.run --discover BA
"""
import datetime as dt
import io
import os
import re
from html import unescape
from urllib.parse import urljoin

from ..padronizar import cotacao, numero, produto_detalhe, sem_acento
from .base import Coletor, parse_data

URL = os.environ.get("CEASA_BA_URL", "https://www.ba.gov.br/sde/boletim-informativo-ceasa-periodo-eleitoral")
# grafias do boletim da BA que diferem do nome padrão (o resto casa sozinho)
APELIDOS = {
    "LARANJA BAHIA": "Laranja Baía",
    "LIMAO TAITI": "Limão Tahiti",
    "MAMAO HAWAI": "Mamão Havaí",
    "MARACUJA": "Maracujá Azedo",
    "LIMA": "Lima da Pérsia",
    "BATATINHA": "Batata",
    "BROCOLI": "Brócolis",
    "PIMENTAO": "Pimentão Verde",
}
SITUACAO_BA = {"EST": "ME", "FIR": "MFI", "FRA": "MFR"}  # -> códigos de padronizar.SITUACAO
NUM = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2}$")
UFS = re.compile(r"^(?:[A-Z]{2}/?)+$")
SECOES = {"FRUTAS", "HORTALICAS", "OVOS", "GRAOS", "CEREAIS", "PESCADOS", "DIVERSOS"}


class ColetorBA(Coletor):
    id = "BA"
    nome = "CEASA - Salvador (BA)"
    uf = "BA"

    def _get(self, page, url):
        r = page.request.get(url, timeout=60000)
        if r.status == 404:
            return None, ""
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status} ao abrir {url}")
        return r.body(), r.headers.get("content-type", "")

    def datas(self, page):
        corpo, _ = self._get(page, URL)
        if corpo is None:
            raise RuntimeError(f"página de boletins não encontrada: {URL} (defina CEASA_BA_URL)")
        out = links_do_html(corpo.decode("utf-8", "replace"), URL)
        if not out:
            raise RuntimeError("nenhum link de boletim na página (o site mudou? rode --discover BA)")
        return out

    def capturar(self, page, ref):
        corpo, tipo = self._get(page, ref)
        if corpo is None:
            return None
        if not corpo.startswith(b"%PDF"):  # página de publicação: procura o PDF dentro dela
            html = corpo.decode("utf-8", "replace")
            pdfs = re.findall(r'href="([^"]+\.pdf)"', html, re.I)
            if not pdfs:
                return None
            corpo, tipo = self._get(page, urljoin(ref, unescape(pdfs[0])))
            if corpo is None or not corpo.startswith(b"%PDF"):
                return None
        linhas = linhas_do_pdf(corpo)
        if not any(len(c) == 7 for *_x, c in linhas):
            return None
        return corpo, "pdf", linhas

    def normalizar(self, linhas, data):
        data_pdf = None
        out, ignoradas = [], []
        for _pag, _ordem, _metodo, cel in linhas:
            if len(cel) == 1:
                if "EMISS" in cel[0].upper():
                    data_pdf = data_pdf or parse_data(cel[0])
                elif norm_secao(cel[0]) not in SECOES:
                    ignoradas.append(cel[0])
                continue
            prod, unid, _proc, mn, com, mx, sit = cel
            c = cotacao(prod, embalagem_ba(unid), mn, com, mx, SITUACAO_BA.get(sit.upper(), ""),
                        apelidos=APELIDOS, data_ok=data_pdf in (None, data))
            if c:
                out.append(c)
            else:
                ignoradas.append(" ".join(cel))
        vistas = {}
        for c in out:  # linha repetida no mesmo boletim: a 2ª ganha " (2)"
            k = (c["produto"], c["detalhe"], c["embalagem"])
            vistas[k] = vistas.get(k, 0) + 1
            if vistas[k] > 1:
                c["detalhe"] = f"{c['detalhe']} ({vistas[k]})".strip()
        novos = sorted({c["produto"] for c in out if produto_detalhe(c["produto"], APELIDOS)[0] is None})
        if novos:
            print(f"[BA] {data}: produtos novos (entram em 'Outros'; cadastre em GRUPOS): {novos}")
        if data_pdf and data_pdf != data:
            print(f"[BA] atenção: boletim pedido para {data}, PDF diz {data_pdf} (linhas ficam 'revisar')")
        revisar = sorted({f"{c['produto']} {c['detalhe']} [{c['embalagem']}]".strip()
                          for c in out if c["conferencia"] != "validado"})
        if revisar or ignoradas:
            fora = revisar + ignoradas
            print(f"[BA] {data}: {len(out) - len(revisar)} validadas; {len(fora)} fora do app: "
                  f"{fora[:10]}{' ...' if len(fora) > 10 else ''}")
        return out

    def discover(self, page, pasta):
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        (pasta / "pagina_inicial.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
        datas = links_do_html(page.content(), URL)
        print(f"{len(datas)} boletins na página. Mais antigos/mais novos:", datas[:3], "...", datas[-3:])
        print(f"Salvei {pasta}/pagina_inicial.html e pagina.png")


def links_do_html(html, base):
    """Links de boletim da página -> [(date, url)] em ordem de data, sem datas/URLs repetidas."""
    por_data = {}
    for href, texto in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        texto = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", texto))).strip()
        if not re.search(r"boletim", texto, re.I) or not re.search(r"ceasa", texto, re.I):
            continue
        url = urljoin(base, unescape(href))
        if not re.match(r"https?://[^/]*ba\.gov\.br/", url):
            continue  # link quebrado no site (ex.: o de 14/08/2026)
        d = data_do_arquivo(url) or parse_data(texto)
        if d and d not in por_data:
            por_data[d] = url
    vistas, out = set(), []
    for d, url in sorted(por_data.items()):
        if url not in vistas:  # mesmo PDF em dois links (ex.: 24/07 apontando para 27-07-2026.pdf)
            vistas.add(url)
            out.append((d, url))
    return out


def data_do_arquivo(url):
    """'.../13-11-2026.pdf', '.../26-10-26.pdf', '.../23-10-2026%20%281%29.pdf' -> date."""
    m = re.search(r"/(\d{2})-(\d{2})-(\d{4}|\d{2})(?=[^/\d]*\.pdf$)", url, re.I)
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    try:
        return dt.date(y + 2000 if y < 100 else y, mth, d)
    except ValueError:
        return None


def linhas_do_pdf(dados):
    """PDF -> [(pagina, ordem, 'pdf', celulas)].
    Linha de preço: 7 células [produto, unidade, procedência, mín, comum, máx, situação].
    Outras linhas úteis (EMISSÃO, nomes de seção) vêm com 1 célula."""
    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        for npag, pag in enumerate(pdf.pages, 1):
            for palavras in _linhas_de_palavras(pag.extract_words()):
                cel = _celulas(palavras)
                texto = " ".join(w["text"] for w in palavras)
                if cel:
                    out.append((npag, len(out), "pdf", cel))
                elif "EMISS" in texto.upper() or norm_secao(texto) in SECOES:
                    out.append((npag, len(out), "pdf", [texto]))
    return out


def _linhas_de_palavras(palavras, tol=3):
    linhas = []
    for w in sorted(palavras, key=lambda w: (round(w["top"]), w["x0"])):
        if linhas and abs(linhas[-1][0]["top"] - w["top"]) <= tol:
            linhas[-1].append(w)
        else:
            linhas.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in linhas]


def _celulas(ws):
    """Lê a linha da direita para a esquerda: situação, máx, comum, mín, procedência;
    o que sobra é produto + unidade, separados pelo maior espaço em branco entre as palavras."""
    ws = list(ws)
    sit = ws.pop()["text"] if ws and re.fullmatch(r"[A-Z]{3}", ws[-1]["text"]) else ""
    nums = []
    while ws and len(nums) < 3 and NUM.match(ws[-1]["text"]):
        nums.insert(0, ws.pop()["text"])
    if len(nums) != 3 or numero(nums[1]) is None:
        return None
    proc = ws.pop()["text"] if ws and UFS.match(ws[-1]["text"]) else ""
    if not ws:
        return None
    gaps = [(ws[i + 1]["x0"] - ws[i]["x1"], i) for i in range(len(ws) - 1)]
    gap, i = max(gaps) if gaps else (0, len(ws) - 1)
    corte = i + 1 if gap > 15 else len(ws)  # sem espaço grande = linha sem unidade
    txt = lambda p: " ".join(w["text"] for w in p)
    return [txt(ws[:corte]), txt(ws[corte:]), proc, *nums, sit]


def norm_secao(t):
    return sem_acento(t).upper().strip()


def embalagem_ba(u):
    """Unidade do boletim da BA -> forma padrão que emb_info entende.
    'CX. 20KG'->'CX 20 KG'; 'SC. C/ 50 kG'->'SC 50 KG'; 'CX. 18 / 20 KG'->'CX 18/20 KG';
    'CX 25 / 27'->'CX 25/27 KG'; 'CX. 30 DUZIAS'->'CX 30 DZ'; 'UND.'->'UN'; 'CENTO'->'CENTO'."""
    e = sem_acento(u or "").upper()
    e = re.sub(r"DUZIAS?", "DZ", e)
    e = e.replace(".", " ")
    e = re.sub(r"\bC/\s*|\bDE\b", " ", e)
    e = re.sub(r"\s*/\s*", "/", e)
    e = re.sub(r"(\d)(KG|DZ)\b", r"\1 \2", e)
    e = re.sub(r"\bUND?\b", "UN", e)
    e = re.sub(r"\s+", " ", e).strip()
    if re.fullmatch(r"(?:CX|SC) [\d,]+(?:/[\d,]+)?", e):  # caixa/saco sem unidade = kg
        e += " KG"
    return e
