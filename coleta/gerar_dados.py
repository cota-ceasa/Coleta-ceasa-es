#!/usr/bin/env python3
"""Gera dados.json (formato do app) a partir de cotações padronizadas.

Uso direto com a planilha antiga:
    python -m coleta.gerar_dados ceasa_consolidado_geral.xlsx docs/dados.json

No fluxo automático, coleta/exportar.py chama gerar() com os dados do banco.

- Usa apenas linhas com Conferência == 'validado'.
- Para cada produto/detalhe/embalagem guarda a cotação mais recente de cada mercado
  e o histórico diário do preço comum (campo "h", alinhado a mercados[].datas).
- Converte preços para a unidade de exibição (kg, dúzia ou unidade).
- Só inclui mercados que têm dados.
"""
import json
import re
import sys

import pandas as pd

# nome do mercado na planilha consolidada -> id usado no app
MERCADO_PLANILHA = {
    "CEASA-Vitória-ES": "ES",
    "CEASA- São Paulo- SP": "SP",
    "CEASA- Belo Horizonte - BH": "MG",
}
ROTULOS = {  # id -> nome exibido (o banco tem a sua própria tabela "ceasa")
    "ES": "CEASA - Vitória (ES)",
    "SP": "CEASA - São Paulo (SP)",
    "MG": "CEASA - Belo Horizonte (MG)",
}

GRUPOS = {
    "folhosas": ["Agrião", "Alface", "Almeirão", "Brócolis", "Chicória", "Couve", "Couve Chinesa",
                 "Couve-flor", "Espinafre", "Mostarda", "Repolho", "Rúcula", "Serralha", "Taioba", "Salsão"],
    "legumes": ["Abóbora", "Abobrinha", "Berinjela", "Chuchu", "Jiló", "Maxixe", "Milho Verde", "Pepino",
                "Pimentão Amarelo", "Pimentão Verde", "Pimentão Vermelho", "Quiabo", "Tomate", "Vagem"],
    "raizes": ["Aipim / Mandioca", "Alho", "Batata", "Batata Doce", "Beterraba", "Cará", "Cebola",
               "Cenoura", "Gengibre", "Inhame"],
    "temperos": ["Alecrim", "Alho-poró", "Cebolinha", "Coentro", "Erva Doce", "Hortelã", "Manjericão", "Salsa",
                 "Sálvia", "Tomilho"],
    "frutas": ["Abacate", "Abacaxi", "Ameixa", "Cacau", "Caju", "Cajamanga", "Graviola", "Nectarina", "Physalis", "Pinha", "Banana Figo", "Banana Maçã", "Banana Nanica", "Banana Ouro",
               "Banana Prata", "Banana Terra", "Coco Seco", "Coco Verde", "Goiaba", "Kiwi", "Laranja Baía",
               "Laranja Lima", "Laranja Pera", "Lima da Pérsia", "Limão Siciliano", "Limão Tahiti",
               "Mamão Formosa", "Mamão Havaí", "Manga", "Maracujá Azedo", "Maçã", "Melancia", "Melão",
               "Morango", "Pêra", "Pêssego", "Tangerina", "Uva (outras)", "Uva Itália", "Uva Niágara", "Uva Passa"],
    "ovos_graos": ["Amendoim", "Farinha de Mandioca", "Feijão Carioca", "Feijão Manteiga", "Feijão Preto",
                   "Feijão Vermelho", "Fubá", "Milho Seco", "Ovos", "Ovos de Codorna"],
    "pescados": ["Atum", "Bacalhau", "Camarão", "Corvina", "Manjuba", "Mistura de Peixes", "Panga", "Pargo", "Pescadinha",
                 "Raia", "Sardinha", "Tainha"],
}
GRUPO_DE = {p: g for g, ps in GRUPOS.items() for p in ps}

# embalagem -> (unidade de exibição, divisor, rótulo da embalagem)
EMB = {
    "KG":          ("kg", 1,  "kg"),
    "CX 30 DZ":    ("dz", 30, "caixa 30 dz"),
    "CX 50 DZ":    ("dz", 50, "caixa 50 dz"),
    "ENG 08 UNID": ("un", 8,  "engradado 8 un"),
    "UN":          ("un", 1,  "unidade"),
    "UN 1,5 KG":   ("un", 1,  "unidade ≈ 1,5 kg"),
    "UN 2,0 KG":   ("un", 1,  "unidade ≈ 2 kg"),
}
GRUPO_PADRAO = "outros"   # produto novo (ainda sem grupo) aparece no app em "Outros"


def grupo_de(produto):
    return GRUPO_DE.get(produto, GRUPO_PADRAO)


def emb_info(emb):
    """(unidade, divisor, rótulo) da embalagem. Conhecidas vêm de EMB; as novas são deduzidas
    do texto ('CX 20 DZ', 'ENG 12 UNID', 'UN 1,2 KG', 'SC 25 KG'...) em vez de descartar a linha."""
    emb = re.sub(r"\s+", " ", (emb or "").strip().upper())
    if emb in EMB:
        return EMB[emb]
    num = lambda t: float(t.replace(",", "."))
    m = re.fullmatch(r"(?:CX|CAIXA)\s+(\d+)\s+DZ", emb)
    if m:
        return ("dz", int(m.group(1)), f"caixa {m.group(1)} dz")
    m = re.fullmatch(r"(?:ENG|CX|SC|PCT|BDJ)\s+(\d+)\s+UNID?", emb)
    if m:
        return ("un", int(m.group(1)), f"{emb.split()[0].lower()} {m.group(1)} un")
    m = re.fullmatch(r"UN\s+([\d.,]+)\s*KG", emb)
    if m:
        return ("un", 1, f"unidade ≈ {m.group(1)} kg")
    m = re.fullmatch(r"(?:CX|SC|PCT|SACO|BDJ|ENG)\s+([\d.,]+)\s*KG", emb)
    if m and num(m.group(1)) > 0:
        return ("kg", num(m.group(1)), "kg")   # preço da embalagem dividido pelo peso -> R$/kg
    if emb in ("UN", "UNID", "UNIDADE"):
        return ("un", 1, "unidade")
    if emb in ("DZ", "DUZIA"):
        return ("dz", 1, "dúzia")
    return None


ABREV = {"ESP": "Especial", "PRIM": "Primeira", "IMP": "Importado", "BCO": "Branco", "VERM": "Vermelho",
         "GRAND": "Grande", "NAC": "Nacional", "EXT": "Extra", "SEG": "Segunda", "ARGENT": "Argentino"}


def limpa_detalhe(d):
    if not isinstance(d, str) or not d.strip():
        return ""
    d = re.sub(r"\bN 5 6\b", "N°5/6", d.strip())
    d = re.sub(r"\bGRAND SMITH\b", "GRANNY SMITH", d)
    palavras = [ABREV.get(w, w) for w in d.split()]
    out = []
    for w in palavras:
        if w in ("A", "AA", "AAA") or re.fullmatch(r"[A-Z]\d", w) or "°" in w:
            out.append(w)
        else:
            out.append(w.capitalize() if w.isupper() else w)
    return " ".join(out)


def gerar(df, saida, rotulos=None):
    """df: colunas Data, Mercado (id), Produto, Detalhe, Embalagem, Min, Com, Max, Sit, Conferência.
    Retorna True se gravou o arquivo."""
    rotulos = rotulos or ROTULOS
    df = df[df["Conferência"] == "validado"].copy()
    df = df[df["Embalagem"].map(lambda e: emb_info(e) is not None)]
    if df.empty:
        print("Nenhuma cotação válida: dados.json não foi alterado.")
        return False
    df["Data"] = pd.to_datetime(df["Data"])
    df["det"] = df["Detalhe"].map(limpa_detalhe)
    df = df.sort_values("Data")

    ordem = list(rotulos)
    ids = sorted(df["Mercado"].unique(), key=lambda m: (ordem.index(m) if m in ordem else len(ordem), m))
    mercados, idx_data = [], {}
    for mid in ids:
        datas = sorted(df.loc[df["Mercado"] == mid, "Data"].unique())
        iso = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in datas]
        idx_data[mid] = {pd.Timestamp(d): n for n, d in enumerate(datas)}
        mercados.append({"id": mid, "nome": rotulos.get(mid, mid), "data": iso[-1], "datas": iso})
    data_mercado = {m["id"]: m["data"] for m in mercados}

    itens = {}
    for (mid, prod, det, emb), g in df.groupby(["Mercado", "Produto", "det", "Embalagem"]):
        g = g.drop_duplicates("Data", keep="last")
        un, div, rot = emb_info(emb)
        chave = f"{prod}|{det}|{emb}"
        it = itens.setdefault(chave, {"k": chave, "p": prod, "d": det, "g": grupo_de(prod),
                                      "u": un, "e": rot, "m": {}})
        h = [None] * len(idx_data[mid])
        for r in g.itertuples(index=False):
            h[idx_data[mid][r.Data]] = round(r.Com / div, 2)
        r = g.iloc[-1]
        num = lambda v: round(v / div, 2) if pd.notna(v) else round(r.Com / div, 2)  # mín/máx ausentes = comum
        reg = {"min": num(r.Min), "com": round(r.Com / div, 2), "max": num(r.Max),
               "s": r.Sit if isinstance(r.Sit, str) else None, "h": h}
        dt = r.Data.strftime("%Y-%m-%d")
        if dt != data_mercado[mid]:
            reg["dt"] = dt  # cotação mais antiga que a data do boletim do mercado
        it["m"][mid] = reg

    lista = sorted(itens.values(), key=lambda i: (i["p"], i["d"], i["k"]))
    out = {"gerado_em": pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M"),
           "mercados": mercados, "itens": lista}
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(lista)} itens, {sum(len(i['m']) for i in lista)} séries, "
          f"{len(mercados)} mercados -> {saida}")
    return True


def main(xlsx, saida):
    df = pd.read_excel(xlsx)
    df = df.rename(columns={"Produto padrão": "Produto", "Mínimo (R$)": "Min", "Comum (R$)": "Com",
                            "Máximo (R$)": "Max", "Situação do mercado": "Sit"})
    df["Mercado"] = df["Mercado"].map(MERCADO_PLANILHA)
    gerar(df.dropna(subset=["Mercado"]), saida)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "dados.json")
