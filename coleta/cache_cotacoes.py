"""Cópia local (cache do GitHub Actions) das cotações validadas, para não baixar o banco inteiro a
cada execução — a cota de transferência do Neon (5 GB/mês) acabava com o histórico completo.

Como funciona: o banco devolve só uma "impressão digital" por boletim (praça × dia: quantidade de
linhas + md5 do conteúdo), calculada lá dentro. Os dias cuja impressão mudou (boletim novo,
renormalização, junção de séries, exclusão) são baixados de novo; o resto vem do arquivo local.
Qualquer dúvida (sem arquivo, cópia com mais de 7 dias, muitos dias mudados, contagem que não
confere, erro) => baixa tudo como antes. No SQLite local, sempre baixa tudo.
"""
import datetime as dt
import gzip
import os
import pickle
from pathlib import Path

import pandas as pd

from . import db

ARQ = Path(os.environ.get("CACHE_COTACOES", "cache/cotacoes.pkl.gz"))
COLUNAS = ["Data", "Mercado", "Produto", "Detalhe", "Embalagem", "Min", "Com", "Max", "Sit", "Conferência"]
VERSAO = 1
DIAS_COMPLETO = 7      # baixa tudo de novo pelo menos 1 vez por semana (rede de segurança)
FRACAO_COMPLETO = 0.3  # se mais de 30% dos dias mudaram, baixar tudo é mais simples

SQL_DIGITAL = (
    "SELECT ceasa_id, data, COUNT(*), md5(string_agg("
    "produto || '|' || detalhe || '|' || embalagem || '|' || COALESCE(minimo::text, '') || '|' || "
    "comum::text || '|' || COALESCE(maximo::text, '') || '|' || COALESCE(situacao, ''), ';' "
    "ORDER BY produto, detalhe, embalagem, comum, minimo, maximo, situacao)) "
    "FROM cotacao WHERE conferencia = 'validado' GROUP BY ceasa_id, data")
SQL_DIAS = ("SELECT data, ceasa_id, produto, detalhe, embalagem, minimo, comum, maximo, situacao, conferencia "
            "FROM cotacao WHERE conferencia = 'validado' AND ceasa_id = %s AND data = ANY(%s)")


def _f(v):
    return None if v is None else float(v)


def _df(linhas):
    return pd.DataFrame([(str(db._data(r[0])), r[1], r[2], r[3], r[4], _f(r[5]), _f(r[6]), _f(r[7]), r[8], r[9])
                         for r in linhas], columns=COLUNAS)


def _ordenar(df):   # mesma ordem da consulta antiga (ORDER BY data, ceasa_id, produto, detalhe)
    return df.sort_values(["Data", "Mercado", "Produto", "Detalhe"], kind="mergesort").reset_index(drop=True)


def _digitais(conn):
    return {(r[0], str(db._data(r[1]))): (int(r[2]), r[3]) for r in conn.consultar(SQL_DIGITAL)}


def _ler():
    try:
        with gzip.open(ARQ, "rb") as f:
            c = pickle.load(f)
        return c if c.get("versao") == VERSAO else None
    except Exception:  # noqa: BLE001 (sem cópia ou arquivo estragado: baixa tudo)
        return None


def _gravar(digitais, df, completo_em):
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARQ.with_suffix(".tmp")
    with gzip.open(tmp, "wb", compresslevel=6) as f:
        pickle.dump({"versao": VERSAO, "digitais": digitais, "df": df, "completo_em": completo_em}, f,
                    protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(ARQ)


def _completo(conn, digitais=None, motivo=""):
    print(f"[cache] baixando todas as cotações do banco{f' ({motivo})' if motivo else ''}")
    df = _ordenar(pd.DataFrame(db.cotacoes_validadas(conn), columns=COLUNAS))
    if conn.pg:
        try:
            _gravar(digitais if digitais is not None else _digitais(conn), df, dt.datetime.now().isoformat())
        except Exception as e:  # noqa: BLE001 (sem cópia local: na próxima baixa tudo de novo)
            print(f"[cache] não consegui gravar a cópia local ({e})")
    return df


def cotacoes(conn):
    """DataFrame das cotações validadas (mesmas colunas e ordem de exportar), usando a cópia local."""
    if not conn.pg:
        return _completo(conn)
    try:
        return _incremental(conn)
    except Exception as e:  # noqa: BLE001  (qualquer problema: comportamento antigo)
        print(f"[cache] cópia local indisponível ({str(e).splitlines()[0][:150]}); baixando tudo")
        return _completo(conn, motivo="falha na cópia local")


def _incremental(conn):
    digitais = _digitais(conn)
    c = _ler()
    if c is None:
        return _completo(conn, digitais, "sem cópia local")
    if dt.datetime.now() - dt.datetime.fromisoformat(c["completo_em"]) > dt.timedelta(days=DIAS_COMPLETO):
        return _completo(conn, digitais, f"cópia com mais de {DIAS_COMPLETO} dias")
    antigos = c["digitais"]
    mudou = sorted(k for k, v in digitais.items() if antigos.get(k) != v)
    saiu = [k for k in antigos if k not in digitais]
    if len(mudou) > FRACAO_COMPLETO * max(len(digitais), 1):
        return _completo(conn, digitais, f"{len(mudou)} de {len(digitais)} dias mudaram")
    df = c["df"]
    if mudou or saiu:
        fora = set(mudou) | set(saiu)
        chave = list(zip(df["Mercado"], df["Data"]))
        df = df[[k not in fora for k in chave]]
        novos = []
        por_ceasa = {}
        for ceasa, data in mudou:
            por_ceasa.setdefault(ceasa, []).append(dt.date.fromisoformat(data))
        for ceasa, datas in por_ceasa.items():
            for i in range(0, len(datas), 200):
                novos.extend(conn.consultar(SQL_DIAS, (ceasa, datas[i:i + 200])))
        df = _ordenar(pd.concat([df, _df(novos)], ignore_index=True))
    # conferência: cada dia tem que ter exatamente as linhas que o banco diz
    cont = df.groupby(["Mercado", "Data"]).size().to_dict()
    if cont != {k: v[0] for k, v in digitais.items()}:
        return _completo(conn, digitais, "contagem da cópia não confere com o banco")
    print(f"[cache] cópia local: {len(df)} cotações; {len(mudou)} dia(s) atualizado(s), {len(saiu)} removido(s)")
    if mudou or saiu:
        _gravar(digitais, df, c["completo_em"])
    return df


def linhas_juncao(df):
    """Formato que juncao.detectar() espera: (ceasa, data, produto, detalhe, embalagem, comum) por ceasa/data."""
    d = df.sort_values(["Mercado", "Data"], kind="mergesort")
    return list(zip(d["Mercado"], d["Data"], d["Produto"], d["Detalhe"], d["Embalagem"], d["Com"]))
