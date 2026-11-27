"""CEASA-PR — 5 unidades (Curitiba, Maringá, Londrina, Foz do Iguaçu, Cascavel), boletins em PDF.

Página do ano (portal Drupal do governo do PR, mesmo tipo de acesso do portal da BA):
  https://www.ceasa.pr.gov.br/Pagina/Cotacao-Diaria-de-Precos-2026
Estrutura: título da unidade ("Curitiba") -> mês ("Novembro") -> "Dia 16" com link para o PDF.
Os nomes dos arquivos não seguem padrão (cotacaopdf16112026.pdf, manovembro_16112026.pdf,
cotacaodiariacascavel16novembro2026.pdf...), por isso a data vem de unidade/mês/dia da página.
Cada unidade vira uma "CEASA" própria no app e no banco.

PDF: cabeçalho "Mercado do Produtor: CEASA - CURITIBA" e "Data da Coleta: 16/11/2026" (usados para
conferir); colunas Produto | Tipo | Unidade/Embalagem | Situação | Min | M_C do dia | Max |
M_C dia anterior | Var % | Procedência. O nome do produto vem numa linha própria ("ABACATE") e as
linhas seguintes trazem a variedade ("AVOCADO"). Células longas quebram em 2 linhas: a leitura é
por coluna (posição x do cabeçalho), juntando os pedaços à linha de preço mais próxima.
Flores e plantas ornamentais ficam de fora; "PRODUTOS AUSENTES" não têm preço.
Se o site mudar, rode:  python -m coleta.run --discover CWB
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

URL_ANO = os.environ.get("CEASA_PR_URL", "https://www.ceasa.pr.gov.br/Pagina/Cotacao-Diaria-de-Precos-{ano}")

# id no app, nome exibido, título da unidade na página, nome no cabeçalho do PDF
UNIDADES = [
    ("CWB", "CEASA - Curitiba (PR)",      "CURITIBA",      "CURITIBA"),
    ("MGA", "CEASA - Maringá (PR)",       "MARINGA",       "MARINGA"),
    ("LDA", "CEASA - Londrina (PR)",      "LONDRINA",      "LONDRINA"),
    ("FOZ", "CEASA - Foz do Iguaçu (PR)", "FOZ DO IGUACU", "FOZ"),
    ("CVL", "CEASA - Cascavel (PR)",      "CASCAVEL",      "CASCAVEL"),
]
MESES = {m: i for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO",
                                     "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"], 1)}
APELIDOS = {
    "BANANA CATURRA": "Banana Nanica",
    "AIPIM MANDIOCA": "Aipim / Mandioca",
    "MANDIOQUINHA BATATA SALSA": "Mandioquinha",
    "MANDIOQUINHA": "Mandioquinha",
    "INHAME TAIA": "Inhame",
    "COUVE BROCOLO": "Brócolis",
    "OVO": "Ovos",
    "LIMAO TAHITI": "Limão Tahiti",
    "LIMAO SICILIANO": "Limão Siciliano",
    "LARANJA BAHIA": "Laranja Baía",
    "MAMAO PAPAYA": "Mamão Havaí",
    "MARACUJA": "Maracujá Azedo",
    "MARACUJA DOCE": "Maracujá Doce",
    "ROMA": "Romã",
    "INHAME": "Inhame",
    "FEIJAO CARIOCA": "Feijão Carioca",
    "FEIJAO PRETO": "Feijão Preto",
}
SITUACAO_PR = {"ESTAVEL": "ME", "FIRME": "MFI", "FRACO": "MFR"}
SECOES_FORA = ("FLORES", "FLOR DE", "PLANTAS", "FORRA", "ORQUIDEA", "PRODUTOS AUSENTES")
NUMW = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")
_BASE = {"CX": "CX", "SC": "SC", "EG": "ENG", "ENG": "ENG", "FD": "FRD", "PC": "PCT", "PCT": "PCT",
         "BD": "BDJ", "BJ": "BDJ", "BDJ": "BDJ"}
_CACHE = {}   # url da página do ano -> índice (as 5 unidades leem a mesma página)


def _kg(v):
    return f"{v:g}".replace(".", ",")


def embalagem_pr(txt):
    """'cx 20 kg'->'CX 20 KG'; 'c/30dz - 25kg'->'CX 30 DZ'; 'mç 400g'->'MOLHO'; 'un 1,5kg'->'UN 1,5 KG';
    'pc 500g'->'PCT 0,5 KG'; 'eg 8 un 15kg'->'ENG 8 UNID'; '50 espigas - 13kg'->'SC 50 UNID'; '01kg'->'KG'."""
    e = re.sub(r"\s+", " ", sem_acento(txt or "").upper()).strip()
    if not e:
        return ""
    peso = None
    m = re.findall(r"([\d]+(?:,\d+)?)\s*(KG|G)\b", e)
    if m:
        n, u = m[-1]
        peso = float(n.replace(",", ".")) / (1000 if u == "G" else 1)
    un = re.search(r"(\d+)\s*(?:UN|UNID|ESPIGAS?)\b", e)
    dz = re.search(r"(\d+)\s*DZ\b", e)
    tipo = re.match(r"[A-Z]+", e)
    tipo = tipo.group(0) if tipo else ""
    if tipo in ("MC", "MACO"):
        return "MOLHO"
    if e.startswith("C/") and dz:
        return f"CX {dz.group(1)} DZ"
    if tipo == "DZ":
        return "DZ"
    if un and tipo not in ("UN",):
        base = _BASE.get(tipo) or ("SC" if "ESPIGA" in e else "CX")
        return f"{base} {un.group(1)} UNID"
    if tipo in ("UN", "CB", "VD"):   # unidade, cabeça (repolho), vidro
        return f"UN {_kg(peso)} KG" if peso else "UN"
    if tipo in _BASE and peso:
        return f"{_BASE[tipo]} {_kg(peso)} KG"
    if not tipo and peso:            # só o peso ('01kg', '200g - 0,20kg')
        return "KG" if peso == 1 else f"PCT {_kg(peso)} KG"
    return e


def _norm(t):
    return re.sub(r"\s+", " ", sem_acento(unescape(t)).upper()).strip()


def indice(html, ano):
    """Página do ano -> {titulo_unidade: {date: url}} (unidade -> mês -> 'Dia NN' com link)."""
    a = html.find('id="main-content"')
    seg = html[a if a >= 0 else 0:]
    seg = re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                 lambda m: f"\n[[{re.sub('<[^>]+>', ' ', m.group(2))}|{m.group(1)}]]\n", seg, flags=re.S | re.I)
    seg = re.sub(r"<(?:br|p|div|h\d|li|tr|td|summary|details|strong|span)\b[^>]*>", "\n", seg, flags=re.I)
    seg = re.sub(r"<[^>]+>", "", seg)
    titulos = {u[2] for u in UNIDADES}
    out, uni, mes = {}, None, None
    for linha in seg.split("\n"):
        t = _norm(linha)
        if not t or t == "&NBSP;":
            continue
        if t in titulos:
            uni, mes = t, None
            continue
        if t.startswith("ANOS ANTERIORES") or t.startswith("[[ANOS ANTERIORES"):
            uni = None
            continue
        if t in MESES:
            mes = MESES[t]
            continue
        m = re.fullmatch(r"\[\[\s*DIA\s*(\d{1,2})\s*\|(.+)\]\]", t)
        if not (m and uni and mes):
            continue
        href = re.search(r"\|(.+)\]\]", linha).group(1).strip()
        if not href.lower().endswith(".pdf"):
            continue
        try:
            d = dt.date(ano, mes, int(m.group(1)))
        except ValueError:
            continue
        out.setdefault(uni, {})[d] = urljoin(URL_ANO.format(ano=ano), unescape(href))  # repetido: vale o último
    return out


class ColetorPR(ColetorBA):
    uf = "PR"
    id = nome = titulo = cabecalho = ""

    def _indice_ano(self, page, ano):
        url = URL_ANO.format(ano=ano)
        if url not in _CACHE:
            self.url_lista = url
            _CACHE[url] = indice(self._abrir(page, url), ano)
        return _CACHE[url]

    def datas(self, page):
        hoje = dt.date.today()
        ini = getattr(self, "inicio", None) or hoje - dt.timedelta(days=30)
        out = {}
        for ano in range(ini.year, hoje.year + 1):
            try:
                out.update(self._indice_ano(page, ano).get(self.titulo, {}))
            except RuntimeError as e:
                if ano == hoje.year:
                    raise
                print(f"[{self.id}] página de {ano} não abriu ({e}); pulando o ano")
        if not out:
            raise RuntimeError(f"nenhum boletim de {self.titulo} na página (o site mudou? rode --discover {self.id})")
        return sorted(out.items())

    def capturar(self, page, ref):
        self.url_lista = re.sub(r"(https?://[^/]+).*", r"\1/", ref)
        corpo = self._baixar(page, ref)
        if not corpo or not corpo.startswith(b"%PDF"):
            return None
        linhas = linhas_do_pdf(corpo)
        if not any(c[0] != "#DATA" for *_x, c in linhas):
            return None
        return corpo, "pdf", linhas

    def normalizar(self, linhas, data):
        data_pdf, mercado, out = None, "", []
        for _pag, _ordem, _met, cel in linhas:
            cel = list(cel)
            if cel[0] == "#DATA":
                data_pdf, mercado = parse_data(cel[1]), _norm(cel[2] if len(cel) > 2 else "")
                continue
            secao, prod, varied, tipo, emb, sit, mn, com, mx, _proc = (cel + [""] * 10)[:10]
            if _norm(secao).startswith(SECOES_FORA) or not prod:
                continue
            mercado_ok = not mercado or self.cabecalho in mercado
            if _norm(tipo) == _norm(varied):   # 'PRIMEIRA | PRIMEIRA'
                tipo = ""
            c = cotacao(f"{prod} {varied} {tipo}", embalagem_pr(emb), mn, com, mx,
                        SITUACAO_PR.get(_norm(sit), ""), apelidos=APELIDOS,
                        data_ok=data_pdf in (None, data) and mercado_ok)
            if c:
                out.append(c)
        vistas = {}
        for c in out:   # mesma linha repetida no boletim: a 2ª ganha " (2)"
            k = (c["produto"], c["detalhe"], c["embalagem"])
            vistas[k] = vistas.get(k, 0) + 1
            if vistas[k] > 1:
                c["detalhe"] = f"{c['detalhe']} ({vistas[k]})".strip()
        if data_pdf and data_pdf != data:
            print(f"[{self.id}] atenção: boletim pedido para {data}, PDF diz {data_pdf} (linhas ficam 'revisar')")
        if mercado and self.cabecalho not in mercado:
            print(f"[{self.id}] atenção: {data}: o PDF é de '{mercado}' (linhas ficam 'revisar')")
        novos = sorted({c["produto"] for c in out if produto_detalhe(c["produto"], APELIDOS)[0] is None})
        if novos:
            print(f"[{self.id}] {data}: {len(novos)} produtos novos (entram em 'Outros'): {novos[:15]}")
        rev = [f"{c['produto']} {c['detalhe']} [{c['embalagem']}]" for c in out if c["conferencia"] != "validado"]
        if rev:
            print(f"[{self.id}] {data}: {len(out) - len(rev)} validadas; {len(rev)} para revisar: {rev[:10]}")
        return out

    def discover(self, page, pasta):
        ano = dt.date.today().year
        try:
            idx = self._indice_ano(page, ano)
        finally:
            (pasta / "pr_pagina.html").write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
        for _i, nome, titulo, _c in UNIDADES:
            ds = sorted(idx.get(titulo, {}))
            print(f"{nome}: {len(ds)} boletins" + (f", {ds[0]} a {ds[-1]}" if ds else ""))
        ds = sorted(idx.get(self.titulo, {}).items())
        if ds:
            r = self.capturar(page, ds[-1][1])
            if r:
                (pasta / f"{self.id}_{ds[-1][0]}.pdf").write_bytes(r[0])
                cots = self.normalizar(r[2], ds[-1][0])
                print(f"\n{self.id} {ds[-1][0]}: {len(cots)} cotações. Primeiras:")
                for c in cots[:8]:
                    print("   ", c)


def linhas_do_pdf(dados):
    """PDF -> [(pagina, ordem, 'pdf', celulas)].
    1ª linha: ['#DATA', 'dd/mm/aaaa', 'CEASA - CURITIBA'].
    Linhas de preço: [seção, produto, variedade, tipo, embalagem, situação, mín, comum, máx, procedência]."""
    import pdfplumber

    out = []
    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        secao, prod, top_prod = "", "", -99
        for npag, pg in enumerate(pdf.pages, 1):
            top_prod = -99   # nova página: o nome do produto continua valendo, mas não se emenda
            ws = pg.extract_words()
            cab = [w for w in ws if w["top"] < 100]
            h = {_norm(w["text"]): w["x0"] for w in cab}
            fim_cab = max((w["bottom"] for w in cab if _norm(w["text"]) in ("EMBALAGEM", "ANTERIOR")), default=95)
            xt = h.get("TIPO", 156) - 16         # início da coluna Tipo
            xe = h.get("UNIDADE", 213) - 8       # Unidade/Embalagem
            xs = h.get("SITUACAO", 267) - 4      # Situação
            xn = h.get("MIN", 311) - 12          # preços
            xp = h.get("PROCEDENCIA", 499) - 8   # procedência
            if npag == 1:
                t = pg.extract_text() or ""
                d = re.search(r"Data da Coleta:\s*(\d{2}/\d{2}/\d{4})", t)
                m = re.search(r"Mercado do Produtor:\s*(.+)", t)
                out.append((1, 0, "pdf", ["#DATA", d.group(1) if d else "", m.group(1).strip() if m else ""]))
            rows = {}
            for w in ws:
                if w["top"] > fim_cab + 2:
                    rows.setdefault(round(w["top"]), []).append(w)
            tops = sorted(rows)
            precos = [t for t in tops if sum(1 for w in rows[t] if NUMW.match(w["text"]) and xn <= w["x0"] < xp) >= 3]
            anexos = {t: [] for t in precos}
            for t in tops:   # pedaços de célula quebrada (tipo/embalagem) acima/abaixo da linha de preço
                if t in precos:
                    continue
                r = sorted(rows[t], key=lambda w: w["x0"])
                perto = [p for p in precos if abs(p - t) <= 9]
                if perto and r[0]["x0"] >= xt - 2 and r[-1]["x0"] < xn:
                    anexos[min(perto, key=lambda p: abs(p - t))].extend(r)
                    rows[t] = None
            for t in tops:
                r = rows[t]
                if r is None:
                    continue
                r = sorted(r, key=lambda w: w["x0"])
                txt = " ".join(w["text"] for w in r)
                if t not in precos:
                    if r[-1]["x0"] >= xt:
                        continue   # rodapé, legenda etc.
                    if r[0]["x0"] < 38:     # título de seção (misto) ou nome do produto (maiúsculas)
                        if txt != txt.upper() or _norm(txt).startswith(SECOES_FORA):
                            secao, prod = txt, ""
                            continue
                        prod = f"{prod} {txt}".strip() if t - top_prod <= 12 and prod else txt
                        top_prod = t
                    elif prod and t - top_prod <= 12:   # nome do produto em 2 linhas
                        prod, top_prod = f"{prod} {txt}", t
                    continue
                todos = r + anexos[t]

                def col(a, b):
                    sel = [w for w in todos if a <= w["x0"] < b]
                    return " ".join(w["text"] for w in sorted(sel, key=lambda w: (round(w["top"]), w["x0"])))
                nums = [w["text"] for w in r if NUMW.match(w["text"]) and xn <= w["x0"] < xp]
                varied = col(0, xt)
                # palavra na margem da linha de preço: é o próprio produto ('CIDRA', sem variedades), a não ser
                # que venha logo abaixo do nome do produto ('ALHO NACIONAL' / 'DESCASCADO') ou comece com número
                if r[0]["x0"] < 38 and t - top_prod > 20 and not varied[:1].isdigit():
                    prod, varied, top_prod = varied, "", -99
                out.append((npag, len(out), "pdf", [secao, prod, varied, col(xt, xe), col(xe, xs), col(xs, xn),
                                                    nums[0], nums[1], nums[2], col(xp, 10 ** 6)]))
    return out


def _criar(id_, nome, titulo, cabecalho):
    return type(f"ColetorPR_{id_}", (ColetorPR,), {"id": id_, "nome": nome, "titulo": titulo,
                                                    "cabecalho": cabecalho})()


COLETORES_PR = [_criar(*u) for u in UNIDADES]
