"""Junção de séries que mudaram de nome no boletim.

Quando a CEASA troca a nomenclatura de um produto (ex.: "Tomate LV" vira "Tomate Longa Vida"),
a série antiga para e uma nova começa logo depois. Este módulo encontra esses pares e junta
a série antiga na nova, com o NOME NOVO, direto no banco (tabela cotacao).

Regras (todas precisam valer):
  - mesma praça e mesmo produto base (o que muda é o detalhe e/ou a embalagem);
  - a série antiga parou de vez (nenhuma cotação nos últimos 60 dias) e tem 10+ cotações;
  - a nova nunca existiu antes e começa entre 3 dias antes e 45 dias depois do fim da antiga;
  - mesma unidade (kg, dúzia ou unidade) e preço coerente: mediana das 10 primeiras cotações
    da nova entre 75% e 133% da mediana das 10 últimas da antiga (em R$ por unidade);
  - sem empate: se houver dois candidatos plausíveis, não junta (fica no log para decidir).

Cada junção fica registrada na tabela juncao e também é aplicada ao renormalizar boletins.
Para desfazer: apague a linha da tabela juncao e rode a coleta com "renormalizar".
"""
import datetime as dt
import math
import statistics

from .gerar_dados import emb_info

SQL_TABELA = """CREATE TABLE IF NOT EXISTS juncao (
    ceasa_id TEXT NOT NULL, produto_de TEXT NOT NULL, detalhe_de TEXT NOT NULL, embalagem_de TEXT NOT NULL,
    produto_para TEXT NOT NULL, detalhe_para TEXT NOT NULL, embalagem_para TEXT NOT NULL,
    fator REAL NOT NULL, motivo TEXT, criado_em TEXT)"""

PAROU_DIAS = 60
JANELA_ANTES, JANELA_DEPOIS = 3, 45
MIN_ANTIGA, MIN_NOVA = 10, 4
RAZAO_MIN, RAZAO_MAX = 0.75, 1.33


def _d(v):
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v)[:10])


def carregar(conn):
    """{(ceasa, produto, detalhe, embalagem) antigo: (produto, detalhe, embalagem, fator) final}"""
    conn.executar(SQL_TABELA)
    mapa = {(r[0], r[1], r[2], r[3]): (r[4], r[5], r[6], float(r[7])) for r in conn.consultar(
        "SELECT ceasa_id, produto_de, detalhe_de, embalagem_de, produto_para, detalhe_para, embalagem_para, fator FROM juncao")}
    # cadeias A -> B -> C viram A -> C (fatores multiplicam)
    for k in list(mapa):
        p, d, e, f = mapa[k]
        vistos = {k}
        while (k[0], p, d, e) in mapa and (k[0], p, d, e) not in vistos:
            vistos.add((k[0], p, d, e))
            p, d, e, f2 = mapa[(k[0], p, d, e)]
            f *= f2
        mapa[k] = (p, d, e, f)
    return mapa


def aplicar_em(cotacoes, ceasa, mapa):
    """Renomeia (e converte o preço de embalagem) nas cotações recém-normalizadas."""
    for c in cotacoes:
        alvo = mapa.get((ceasa, c["produto"], c["detalhe"], c["embalagem"]))
        if alvo:
            c["produto"], c["detalhe"], c["embalagem"], f = alvo
            for campo in ("minimo", "comum", "maximo"):
                if c.get(campo) is not None:
                    c[campo] = round(float(c[campo]) * f, 4)
    return cotacoes


def detectar(conn, aplicar=True):
    conn.executar(SQL_TABELA)
    linhas = conn.consultar("SELECT ceasa_id, data, produto, detalhe, embalagem, comum FROM cotacao "
                            "WHERE conferencia = 'validado' ORDER BY ceasa_id, data")
    series, fim_mercado = {}, {}
    for ceasa, data, prod, det, emb, com in linhas:
        info = emb_info(emb)
        if not info or com is None:
            continue
        data = _d(data)
        fim_mercado[ceasa] = max(fim_mercado.get(ceasa, data), data)
        series.setdefault((ceasa, prod, det, emb), []).append((data, float(com) / info[1]))
    juncoes = []
    usadas = set()
    for (ceasa, prod, det, emb), pa in series.items():
        ua = emb_info(emb)[0]
        fim_a = pa[-1][0]
        if len(pa) < MIN_ANTIGA or (fim_mercado[ceasa] - fim_a).days < PAROU_DIAS:
            continue
        ref_a = statistics.median(v for _, v in pa[-10:])
        cands = []
        for (c2, p2, d2, e2), pb in series.items():
            if c2 != ceasa or p2 != prod or (d2, e2) == (det, emb) or emb_info(e2)[0] != ua or len(pb) < MIN_NOVA:
                continue
            ini_b = pb[0][0]
            if not (-JANELA_ANTES <= (ini_b - fim_a).days <= JANELA_DEPOIS) or ini_b <= pa[0][0]:
                continue
            razao = statistics.median(v for _, v in pb[:10]) / ref_a
            if RAZAO_MIN <= razao <= RAZAO_MAX:
                cands.append((abs(math.log(razao)), (ini_b - fim_a).days, (d2, e2), razao))
        if not cands:
            if not aplicar:   # simulação: mostra o candidato mais próximo que não passou nas regras
                quase = []
                for (c2, p2, d2, e2), pb in series.items():
                    if c2 != ceasa or p2 != prod or (d2, e2) == (det, emb) or len(pb) < MIN_NOVA:
                        continue
                    gap = (pb[0][0] - fim_a).days
                    if -30 <= gap <= 365:
                        r = statistics.median(v for _, v in pb[:10]) / ref_a
                        nova = "nova" if pb[0][0] > pa[0][0] else "já existia"
                        quase.append((abs(gap), f"«{d2}» [{e2}] começou {gap:+d} d, preço x{r:.2f}, {nova}, un {emb_info(e2)[0]}"))
                if quase:
                    print(f"[quase] {ceasa} {prod} «{det}» [{emb}] parou {fim_a:%d/%m/%Y} ({len(pa)} cot.): "
                          + "; ".join(q for _, q in sorted(quase)[:3]))
            continue
        cands.sort()
        if len(cands) > 1 and cands[1][0] - cands[0][0] < 0.05:
            print(f"[junção] {ceasa} {prod} {det} [{emb}]: candidatos empatados {[c[2] for c in cands[:3]]}; não juntei")
            continue
        _, gap, (d2, e2), razao = cands[0]
        if (ceasa, prod, d2, e2) in usadas:
            print(f"[junção] {ceasa} {prod} {d2} [{e2}] já recebe outra série antiga; {det} [{emb}] ficou de fora")
            continue
        usadas.add((ceasa, prod, d2, e2))
        fator = emb_info(e2)[1] / emb_info(emb)[1]   # preço por embalagem antiga -> por embalagem nova
        motivo = (f"antiga parou em {fim_a:%d/%m/%Y}; nova começou {gap:+d} dias depois; "
                  f"preço novo/antigo = {razao:.2f}")
        juncoes.append((ceasa, prod, det, emb, prod, d2, e2, fator, motivo))
    for j in juncoes:
        print(f"[junção] {j[0]} {j[1]} «{j[2]}» [{j[3]}] -> «{j[5]}» [{j[6]}] ({j[8]})")
    if aplicar and juncoes:
        agora = dt.datetime.now().isoformat(timespec="seconds")
        for (ceasa, p1, d1, e1, p2, d2, e2, f, motivo) in juncoes:
            conn.executar("INSERT INTO juncao VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (ceasa, p1, d1, e1, p2, d2, e2, f, motivo, agora))
            conn.executar("UPDATE cotacao SET produto = %s, detalhe = %s, embalagem = %s, "
                          "minimo = minimo * %s, comum = comum * %s, maximo = maximo * %s "
                          "WHERE ceasa_id = %s AND produto = %s AND detalhe = %s AND embalagem = %s",
                          (p2, d2, e2, f, f, f, ceasa, p1, d1, e1))
        conn.commit()
        print(f"[junção] {len(juncoes)} série(s) antiga(s) juntada(s) à nova")
    elif not juncoes:
        print("[junção] nenhuma troca de nome encontrada")
    return juncoes
