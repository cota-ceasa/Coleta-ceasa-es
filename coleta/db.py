"""Banco da coleta. Postgres (Neon/Supabase) quando existe DATABASE_URL; senão um arquivo
SQLite local (coleta.db) para testar no seu computador sem criar conta em nada."""
import datetime as dt
import json
import os
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")
SQLITE_ARQ = os.environ.get("COLETA_SQLITE", "coleta.db")
DIAS_RETENTAR = 4   # boletim "sem dados" de datas recentes é tentado de novo (o site pode publicar depois)


class Conexao:
    def __init__(self, raw, postgres):
        self.raw, self.pg = raw, postgres

    def _sql(self, sql):
        return sql if self.pg else sql.replace("%s", "?")

    def executar(self, sql, params=()):
        cur = self.raw.cursor()
        cur.execute(self._sql(sql), params)
        return cur

    def varios(self, sql, lista):
        if lista:
            cur = self.raw.cursor()
            cur.executemany(self._sql(sql), lista)

    def consultar(self, sql, params=()):
        cur = self.executar(sql, params)
        return cur.fetchall()

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def conectar():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        import psycopg  # instalado via requirements.txt
        conn = Conexao(psycopg.connect(url), True)
    else:
        import sqlite3
        print(f"[db] DATABASE_URL não definida: usando o arquivo local {SQLITE_ARQ}")
        conn = Conexao(sqlite3.connect(SQLITE_ARQ), False)
    sem_comentarios = "\n".join(l.split("--")[0] for l in SCHEMA.read_text(encoding="utf-8").splitlines())
    for cmd in sem_comentarios.split(";"):
        if cmd.strip():
            conn.executar(cmd)
    conn.commit()
    return conn


def _agora():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def registrar_ceasas(conn, coletores):
    for c in coletores:
        conn.executar(
            "INSERT INTO ceasa (id, nome, uf) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET nome = excluded.nome, uf = excluded.uf",
            (c.id, c.nome, c.uf))
    conn.commit()


def datas_resolvidas(conn, ceasa):
    """Datas que não precisam ser baixadas de novo: 'ok' e 'sem_dados' antigos.
    'erro' e 'sem_dados' recentes são tentados outra vez."""
    corte = (dt.date.today() - dt.timedelta(days=DIAS_RETENTAR)).isoformat()
    linhas = conn.consultar(
        "SELECT data FROM boletim WHERE ceasa = %s AND (status = 'ok' OR (status = 'sem_dados' AND data < %s))",
        (ceasa, corte))
    return {dt.date.fromisoformat(r[0]) for r in linhas}


def gravar_boletim(conn, ceasa, data, status, hash=None, linhas=None, erro=None):
    d = data.isoformat()
    conn.executar(
        "INSERT INTO boletim (ceasa, data, status, hash, erro, normalizado, atualizado) "
        "VALUES (%s, %s, %s, %s, %s, 0, %s) "
        "ON CONFLICT (ceasa, data) DO UPDATE SET status = excluded.status, hash = excluded.hash, "
        "erro = excluded.erro, normalizado = 0, atualizado = excluded.atualizado",
        (ceasa, d, status, hash, erro, _agora()))
    if linhas is not None:
        conn.executar("DELETE FROM linha_bruta WHERE ceasa = %s AND data = %s", (ceasa, d))
        conn.varios(
            "INSERT INTO linha_bruta (ceasa, data, ordem, pagina, metodo, celulas) VALUES (%s, %s, %s, %s, %s, %s)",
            [(ceasa, d, i, pag, met, json.dumps(cel, ensure_ascii=False))
             for i, (pag, _ordem, met, cel) in enumerate(linhas)])
    conn.commit()


def pendentes_normalizacao(conn, ceasa):
    return [dt.date.fromisoformat(r[0]) for r in conn.consultar(
        "SELECT data FROM boletim WHERE ceasa = %s AND status = 'ok' AND normalizado = 0 ORDER BY data", (ceasa,))]


def linhas(conn, ceasa, data):
    """[(pagina, ordem, metodo, [celulas])] na ordem original."""
    return [(r[0], r[1], r[2], json.loads(r[3])) for r in conn.consultar(
        "SELECT pagina, ordem, metodo, celulas FROM linha_bruta WHERE ceasa = %s AND data = %s ORDER BY ordem",
        (ceasa, data.isoformat()))]


def gravar_cotacoes(conn, ceasa, data, cotacoes):
    d = data.isoformat()
    conn.executar("DELETE FROM cotacao WHERE ceasa = %s AND data = %s", (ceasa, d))
    conn.varios(
        "INSERT INTO cotacao (ceasa, data, ordem, produto, detalhe, embalagem, minimo, comum, maximo, "
        "situacao, conferencia) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [(ceasa, d, i, c["produto"], c["detalhe"], c["embalagem"], c["minimo"], c["comum"], c["maximo"],
          c["situacao"], c["conferencia"]) for i, c in enumerate(cotacoes)])
    conn.executar("UPDATE boletim SET normalizado = 1 WHERE ceasa = %s AND data = %s", (ceasa, d))
    conn.commit()


def renormalizar(conn, ceasa):
    """Marca todos os boletins para serem normalizados de novo (use depois de melhorar o parser)."""
    conn.executar("UPDATE boletim SET normalizado = 0 WHERE ceasa = %s AND status = 'ok'", (ceasa,))
    conn.commit()


def cotacoes_validadas(conn):
    return conn.consultar(
        "SELECT data, ceasa, produto, detalhe, embalagem, minimo, comum, maximo, situacao, conferencia "
        "FROM cotacao WHERE conferencia = 'validado' ORDER BY data, ceasa, ordem")


def rotulos(conn):
    return {r[0]: r[1] for r in conn.consultar("SELECT id, nome FROM ceasa ORDER BY id")}
