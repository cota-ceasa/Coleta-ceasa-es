"""Banco -> docs/dados.json (formato do app)."""
import pandas as pd

from . import db
from .gerar_dados import gerar

COLUNAS = ["Data", "Mercado", "Produto", "Detalhe", "Embalagem", "Min", "Com", "Max", "Sit", "Conferência"]


def exportar(conn, saida):
    df = pd.DataFrame(db.cotacoes_validadas(conn), columns=COLUNAS)
    if df.empty:
        print("[exportar] nenhuma cotação validada no banco: dados.json não foi alterado.")
        return False
    return gerar(df, saida, db.rotulos(conn))
