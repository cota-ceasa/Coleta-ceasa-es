"""Extrai séries do banco para estudos (ex.: backtest da previsão da análise anual).

  python -m coleta.estudo ES Tangerina      # imprime as séries validadas do produto, uma por linha (JSON)
"""
import json
import sys

from . import db
from .gerar_dados import emb_info


def main(ceasa, produto):
    conn = db.conectar()
    linhas = conn.consultar(
        "SELECT data, detalhe, embalagem, comum FROM cotacao WHERE ceasa_id = %s AND produto = %s "
        "AND conferencia = 'validado' ORDER BY detalhe, embalagem, data", (ceasa, produto))
    datas = [str(r[0])[:10] for r in conn.consultar(
        "SELECT DISTINCT data FROM cotacao WHERE ceasa_id = %s ORDER BY data", (ceasa,))]
    series = {}
    for data, det, emb, com in linhas:
        info = emb_info(emb)
        if info and com is not None:
            series.setdefault(f"{det}|{emb}", {}).__setitem__(str(data)[:10], round(float(com) / info[1], 4))
    print("ESTUDO_DATAS " + json.dumps(datas))
    for k, v in series.items():
        print("ESTUDO_SERIE " + json.dumps({"k": k, "pts": v}, ensure_ascii=False))
    conn.close()


if __name__ == "__main__":
    main(*sys.argv[1:3])
