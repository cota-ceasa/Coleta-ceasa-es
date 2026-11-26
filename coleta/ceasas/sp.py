"""CEAGESP - Entreposto da Capital (São Paulo) — formulário WordPress em ceagesp.gov.br/cotacoes/.

Formulário (POST para a própria página):
  cot_grupo = DIVERSOS | FLORES | FRUTAS | LEGUMES | ORGÂNICOS | PESCADOS | VERDURAS
  cot_data  = dd/mm/aaaa
As datas disponíveis por categoria vêm no JavaScript da página: var Grupos = {"FRUTAS": [...], ...}
(só os boletins recentes; o site publica seg, qua e sex).

Resultado: tabela .contacao_lista, título "Categoria: FRUTAS  Data: 13/11/2026" e colunas
  Produto | Classificação | Uni/Peso | Menor | Comun | Maior | Quilo
"Quilo" é o peso da unidade em kg (ex.: ABACAXI | UN | ... | 2,2 ; AMENDOIM | SC | ... | 25).
Um boletim do app = uma data com todas as categorias.

Interior (Ribeirão Preto, Campinas, Sorocaba...): a CEAGESP não publica no próprio site, manda
para o painel Prohort/Conab. Veja ceasas/prohort.py (por ora só inspeção: --discover PROHORT).
Se o site mudar, rode:  python -m coleta.run --discover SP
"""
import json
import os
import re
from html import unescape

from ..padronizar import cotacao, norm, produto_detalhe
from .base import Coletor, parse_data

URL = os.environ.get("CEAGESP_URL", "https://ceagesp.gov.br/cotacoes/")
# FLORES fica de fora por padrão (não é alimento; o app não tem grupo para elas).
# Para incluir: variável CEAGESP_GRUPOS="DIVERSOS,FLORES,FRUTAS,..."
GRUPOS = [g.strip() for g in os.environ.get(
    "CEAGESP_GRUPOS", "FRUTAS,LEGUMES,VERDURAS,DIVERSOS,PESCADOS,ORGÂNICOS").split(",") if g.strip()]

# grafias da CEAGESP que diferem do nome padrão (chaves já normalizadas: sem acento, maiúsculas)
APELIDOS = {
    "ABACATE AVOCADO": "Abacate", "ABACAXI HAVAI": "Abacaxi", "ABACAXI PEROLA": "Abacaxi",
    "BANANA NANICA": "Banana Nanica", "BANANA MACA": "Banana Maçã", "BANANA PRATA": "Banana Prata",
    "BANANA TERRA": "Banana Terra", "BANANA OURO": "Banana Ouro",
    "COCO VERDE": "Coco Verde", "COCO SECO": "Coco Seco",
    "LARANJA BAIA": "Laranja Baía", "LARANJA BAHIA": "Laranja Baía", "LARANJA LIMA": "Laranja Lima",
    "LARANJA PERA": "Laranja Pera", "LARANJA VALENCIA": "Laranja Valência", "LARANJA SELETA": "Laranja Seleta",
    "LARANJA NATAL": "Laranja Natal", "LIMAO TAHITI": "Limão Tahiti", "LIMAO TAITI": "Limão Tahiti",
    "LIMAO SICILIANO": "Limão Siciliano", "LIMAO GALEGO": "Limão Galego",
    "MAMAO FORMOSA": "Mamão Formosa", "MAMAO HAVAI": "Mamão Havaí", "MAMAO PAPAIA": "Mamão Havaí",
    "MARACUJA AZEDO": "Maracujá Azedo", "MARACUJA DOCE": "Maracujá Doce",
    "UVA ITALIA": "Uva Itália", "UVA NIAGARA": "Uva Niágara", "PERA": "Pêra", "PESSEGO": "Pêssego",
    "MACA": "Maçã", "MELAO": "Melão", "CAQUI": "Caqui", "TANGERINA": "Tangerina", "MEXERICA": "Tangerina",
    "PONKAN": "Tangerina", "MURCOTE": "Tangerina",
    "CEBOLA": "Cebola", "ALHO": "Alho", "BATATA DOCE": "Batata Doce", "MANDIOCA": "Aipim / Mandioca",
    "MANDIOQUINHA": "Mandioquinha", "PIMENTAO AMARELO": "Pimentão Amarelo",
    "PIMENTAO VERDE": "Pimentão Verde", "PIMENTAO VERMELHO": "Pimentão Vermelho",
    "ABOBORA": "Abóbora", "ABOBRINHA": "Abobrinha", "BERINJELA": "Berinjela", "CHUCHU": "Chuchu",
    "JILO": "Jiló", "PEPINO": "Pepino", "QUIABO": "Quiabo", "TOMATE": "Tomate", "VAGEM": "Vagem",
    "MILHO VERDE": "Milho Verde", "ERVILHA TORTA": "Ervilha Torta",
    "COUVE FLOR": "Couve-flor", "ALFACE": "Alface", "AGRIAO": "Agrião", "ESPINAFRE": "Espinafre",
    "RUCULA": "Rúcula", "REPOLHO": "Repolho", "SALSAO": "Salsão", "SALSA": "Salsa",
    "CEBOLINHA": "Cebolinha", "COENTRO": "Coentro", "HORTELA": "Hortelã", "MANJERICAO": "Manjericão",
    "ALHO PORO": "Alho-poró", "ALMEIRAO": "Almeirão", "CHICORIA": "Chicória", "ESCAROLA": "Chicória",
    "OVOS": "Ovos", "OVO": "Ovos", "OVOS DE CODORNA": "Ovos de Codorna",
    "AMENDOIM": "Amendoim", "PINHAO": "Pinhão",
    "TILAPIA": "Tilápia", "CORVINA": "Corvina", "SARDINHA": "Sardinha", "PESCADA": "Pescada",
    "CACAO": "Cação", "CAMARAO": "Camarão", "MISTURA AGUA SALGADA": "Mistura de Peixes",
    "PANGASIUS": "Panga", "ANCHOVAS": "Anchova",
}
_UNIDADE = {"CX": "CX", "CAIXA": "CX", "ENG": "ENG", "ENGR": "ENG", "ENGRADADO": "ENG",
            "SC": "SC", "SACO": "SC", "SACA": "SC", "PCT": "PCT", "PACOTE": "PCT",
            "BDJ": "BDJ", "BANDEJA": "BDJ", "FRD": "FRD", "FARDO": "FRD"}
CEL = ["#GRUPO", "PRODUTO", "CLASSIF", "UNIDADE", "MENOR", "COMUM", "MAIOR", "QUILO"]


def _texto(x):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def preco(txt):
    """'1.234,56' / '17,5' / '17.5' -> '1234,56' / '17,5' / '17,5' (formato que padronizar entende).
    O site já mostrou preço com ponto decimal; padronizar.numero() leria '17.5' como 175."""
    t = (txt or "").strip().replace(" ", "")
    if not re.fullmatch(r"[\d.,]+", t):
        return ""
    if "," in t:
        return t.replace(".", "")
    if re.fullmatch(r"\d+\.\d{1,2}", t):        # ponto decimal
        return t.replace(".", ",")
    return t.replace(".", "")                   # ponto de milhar (1.234)


def embalagem(unid, quilo):
    """Uni/Peso + Quilo -> embalagem no padrão do app (emb_info): KG, DZ, MOLHO, 'UN 2,2 KG', 'SC 25 KG'."""
    u = norm(unid)
    q = preco(quilo)
    qn = float(q.replace(",", ".")) if q else None
    if u in ("KG", "QUILO", "QUILOS"):
        return "KG"
    if u in ("DZ", "DUZIA"):
        return "DZ"
    if u.startswith(("MACO", "MC", "MOLHO")):
        return "MOLHO"
    if u == "CENTO":
        return "CENTO"
    if u in ("UN", "UNID", "UND", "UNIDADE"):
        return f"UN {q} KG" if qn and qn != 1 else "UN"
    base = _UNIDADE.get(u.split()[0] if u else "")
    if base and qn:
        return f"{base} {q} KG"   # preço da embalagem / peso -> R$/kg no app
    return u


def tabelas(html):
    """Resultado do POST -> (grupo, data, [linhas]) de cada tabela de cotação da página.
    As colunas são achadas pelo cabeçalho, então mudança de ordem não quebra a leitura."""
    out = []
    for m in re.finditer(r"<table\b[^>]*>(.*?)</table>", html, re.S | re.I):
        trs = [[_texto(c) for c in re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", tr, re.S | re.I)]
               for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", m.group(1), re.S | re.I)]
        cab, idx = None, {}
        for i, cel in enumerate(trs):
            n = [norm(c) for c in cel]
            if any(c.startswith("MENOR") for c in n) and any(c.startswith("COMU") for c in n):
                cab = i
                for j, c in enumerate(n):
                    for chave, pref in (("PRODUTO", "PRODUTO"), ("CLASSIF", "CLASSIF"), ("UNIDADE", "UNI"),
                                        ("MENOR", "MENOR"), ("COMUM", "COMU"), ("MAIOR", "MAIOR"),
                                        ("QUILO", "QUILO")):
                        if c.startswith(pref) and chave not in idx:
                            idx[chave] = j
                break
        if cab is None or "PRODUTO" not in idx or "COMUM" not in idx:
            continue
        # título "Categoria: FRUTAS Data: 13/11/2026": na própria tabela ou logo antes dela
        antes = _texto(html[max(0, m.start() - 800):m.start()])
        titulo = " ".join(" ".join(c) for c in trs[:cab]) or antes
        g = re.search(r"Categoria:?\s*([A-ZÀ-Ú]+)", titulo, re.I) or re.search(r"Categoria:?\s*([A-ZÀ-Ú]+)", antes, re.I)
        d = re.search(r"Data:?\s*(\d{2}/\d{2}/\d{4})", titulo) or re.search(r"Data:?\s*(\d{2}/\d{2}/\d{4})", antes)
        linhas = []
        for cel in trs[cab + 1:]:
            if len(cel) <= idx["COMUM"]:
                continue
            pega = lambda k: cel[idx[k]] if k in idx and idx[k] < len(cel) else ""
            if not pega("PRODUTO"):
                continue
            linhas.append([pega(k) for k in CEL[1:]])
        out.append((g.group(1).upper() if g else "", parse_data(d.group(1)) if d else None, linhas))
    return out


class ColetorSP(Coletor):
    id = "SP"   # mesmo id da planilha antiga ("CEASA- São Paulo- SP"): o histórico continua
    nome = "CEAGESP - São Paulo (SP)"
    uf = "SP"

    def _mapa(self, page):
        """{grupo: [datas]} lido do 'var Grupos' da página."""
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        html = page.content()
        m = re.search(r"var\s+Grupos\s*=\s*(\{.*?\})\s*;", html, re.S)
        if not m:
            raise RuntimeError("formulário mudou: 'var Grupos' não encontrado (rode --discover SP)")
        bruto = json.loads(m.group(1))
        mapa = {}
        for g, ds in bruto.items():
            if norm(g) in {norm(x) for x in GRUPOS}:
                mapa[g] = {parse_data(x) for x in ds} - {None}
        if not mapa:
            raise RuntimeError(f"nenhuma das categorias {GRUPOS} está no site (há: {list(bruto)})")
        self._grupos = mapa
        return mapa

    def datas(self, page):
        mapa = self._mapa(page)
        todas = sorted(set().union(*mapa.values()))
        return [(d, d.strftime("%d/%m/%Y")) for d in todas]

    def _consultar(self, page, grupo, ref):
        r = page.request.post(URL, form={"cot_grupo": grupo, "cot_data": ref}, timeout=90000)
        if not r.ok:
            raise RuntimeError(f"{grupo} {ref}: HTTP {r.status}")
        return r.text()

    def capturar(self, page, ref):
        """Uma data = todas as categorias. Retorna (html, 'html', linhas) ou None se nada vier."""
        d = parse_data(ref)
        mapa = getattr(self, "_grupos", None) or self._mapa(page)
        partes, linhas = [], []
        for grupo, ds in mapa.items():
            if d not in ds:
                continue
            html = self._consultar(page, grupo, ref)
            achadas = tabelas(html)
            if not achadas:
                print(f"[SP] {ref} {grupo}: a página não trouxe tabela de cotação")
                continue
            for g, data_tab, rows in achadas:
                linhas.append((len(partes) + 1, 0, "html", ["#DATA", g or grupo,
                                                            data_tab.isoformat() if data_tab else ""]))
                for i, cel in enumerate(rows, 1):
                    linhas.append((len(partes) + 1, i, "html", [g or grupo] + cel))
            ini = html.find('id="cotacao"')
            partes.append(f"<!-- {grupo} -->\n" + (html[ini:] if ini >= 0 else html))
            page.wait_for_timeout(800)   # pausa educada entre categorias
        if not any(c[0] != "#DATA" for *_x, c in linhas):
            return None
        return "\n".join(partes).encode("utf-8"), "html", linhas

    def normalizar(self, linhas, data):
        out, datas_erradas = [], set()
        data_grupo = {}
        for _pag, _ordem, _met, cel in linhas:
            cel = list(cel)
            if cel and cel[0] == "#DATA":
                data_grupo[cel[1]] = parse_data(cel[2]) if len(cel) > 2 else None
                continue
            grupo, prod, classif, unid, mn, com, mx, quilo = (cel + [""] * 8)[:8]
            classif = "" if classif.strip() in ("-", "--") else classif
            dg = data_grupo.get(grupo)
            if dg and dg != data:
                datas_erradas.add(grupo)
            c = cotacao(f"{prod} {classif}".strip(), embalagem(unid, quilo), preco(mn), preco(com), preco(mx),
                        "", apelidos=APELIDOS, data_ok=dg in (None, data))
            if c:
                out.append(c)
        vistas = {}
        for c in out:   # mesma linha repetida no boletim: a 2ª ganha " (2)"
            k = (c["produto"], c["detalhe"], c["embalagem"])
            vistas[k] = vistas.get(k, 0) + 1
            if vistas[k] > 1:
                c["detalhe"] = f"{c['detalhe']} ({vistas[k]})".strip()
        novos = sorted({c["produto"] for c in out if produto_detalhe(c["produto"], APELIDOS)[0] is None})
        if novos:
            print(f"[SP] {data}: {len(novos)} produtos novos (entram em 'Outros'): {novos[:20]}")
        if datas_erradas:
            print(f"[SP] atenção: {data}: tabela com outra data em {sorted(datas_erradas)} (linhas ficam 'revisar')")
        rev = [f"{c['produto']} {c['detalhe']} [{c['embalagem']}]" for c in out if c["conferencia"] != "validado"]
        if rev:
            print(f"[SP] {data}: {len(out) - len(rev)} validadas; {len(rev)} para revisar: {rev[:10]}")
        return out

    def discover(self, page, pasta):
        mapa = self._mapa(page)
        (pasta / "sp_pagina.html").write_text(page.content(), encoding="utf-8")
        for g, ds in mapa.items():
            print(f"{g}: {len(ds)} datas, {min(ds)} a {max(ds)}" if ds else f"{g}: sem datas")
        g = next(iter(mapa))
        d = max(mapa[g])
        html = self._consultar(page, g, d.strftime("%d/%m/%Y"))
        (pasta / "sp_resultado.html").write_text(html, encoding="utf-8")
        for grupo, data_tab, rows in tabelas(html):
            print(f"\nTabela {grupo} {data_tab}: {len(rows)} linhas. Primeiras:")
            for r in rows[:5]:
                print("   ", r, "->", embalagem(r[2], r[6]))
        page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
        print(f"Salvei {pasta}/sp_pagina.html, sp_resultado.html e pagina.png")
