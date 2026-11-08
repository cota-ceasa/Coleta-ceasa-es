"""Banco da coleta: Postgres (Neon/Supabase) quando existe DATABASE_URL; senão um arquivo
SQLite local (coleta.db) para testar no seu computador sem criar conta em nada.

Usa as tabelas ceasa, boletim, linha_bruta e cotacao (colunas ceasa_id, pdf_sha256, ...),
no mesmo formato das que já existem no Neon. Não depende de chaves/índices das tabelas:
"gravar" é sempre apagar o dia e inserir de novo."""
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
        self.celulas_array = False   # no Neon antigo, linha_bruta.celulas é text[]

    def _sql(self, sql):
        return sql if self.pg else sql.replace("%s", "?")

    def d(self, data):
        """date -> o que o banco espera (Postgres: date; SQLite: texto ISO)."""
        return data if self.pg else data.isoformat()

    def executar(self, sql, params=()):
        cur = self.raw.cursor()
        try:
            cur.execute(self._sql(sql), params)
        except Exception:
            self.raw.rollback()   # sem isso o Postgres recusa todos os comandos seguintes
            raise
        return cur

    def varios(self, sql, lista):
        if lista:
            cur = self.raw.cursor()
            try:
                cur.executemany(self._sql(sql), lista)
            except Exception:
                self.raw.rollback()
                raise

    def consultar(self, sql, params=()):
        return self.executar(sql, params).fetchall()

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def _data(v):
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v)[:10])


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
    if conn.pg:
        tipo = conn.consultar(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'linha_bruta' AND column_name = 'celulas'")
        conn.celulas_array = bool(tipo) and tipo[0][0] == "ARRAY"
    return conn


def registrar_ceasas(conn, coletores):
    for c in coletores:
        cur = conn.executar("UPDATE ceasa SET nome = %s, uf = %s WHERE id = %s", (c.nome, c.uf, c.id))
        if cur.rowcount == 0:
            conn.executar("INSERT INTO ceasa (id, nome, uf, ativo) VALUES (%s, %s, %s, TRUE)", (c.id, c.nome, c.uf))
    conn.commit()


def datas_resolvidas(conn, ceasa):
    """Datas que não precisam ser baixadas de novo: 'ok' e 'sem_dados' antigos.
    'erro' e 'sem_dados' recentes são tentados outra vez."""
    corte = dt.date.today() - dt.timedelta(days=DIAS_RETENTAR)
    linhas = conn.consultar(
        "SELECT data FROM boletim WHERE ceasa_id = %s AND (status = 'ok' OR (status = 'sem_dados' AND data < %s))",
        (ceasa, conn.d(corte)))
    return {_data(r[0]) for r in linhas}


def gravar_boletim(conn, ceasa, data, status, hash=None, linhas=None, erro=None):
    agora = dt.datetime.now(dt.timezone.utc)
    agora = agora if conn.pg else agora.strftime("%Y-%m-%d %H:%M:%S")
    d = conn.d(data)
    tent = 1 if status == "erro" else 0
    cur = conn.executar(
        "UPDATE boletim SET status = %s, pdf_sha256 = %s, erro = %s, normalizado = FALSE, coletado_em = %s, "
        "tentativas = CASE WHEN %s = 1 THEN COALESCE(tentativas, 0) + 1 ELSE COALESCE(tentativas, 0) END "
        "WHERE ceasa_id = %s AND data = %s",
        (status, hash, erro, agora, tent, ceasa, d))
    if cur.rowcount == 0:
        conn.executar(
            "INSERT INTO boletim (ceasa_id, data, status, pdf_sha256, erro, tentativas, normalizado, coletado_em) "
            "VALUES (%s, %s, %s, %s, %s, %s, FALSE, %s)",
            (ceasa, d, status, hash, erro, tent, agora))
    if linhas is not None:
        conn.executar("DELETE FROM linha_bruta WHERE ceasa_id = %s AND data = %s", (ceasa, d))
        conn.varios(
            "INSERT INTO linha_bruta (ceasa_id, data, pagina, ordem, metodo, celulas) VALUES (%s, %s, %s, %s, %s, %s)",
            [(ceasa, d, pag, i, met, list(cel) if conn.celulas_array else json.dumps(cel, ensure_ascii=False))
             for i, (pag, _ordem, met, cel) in enumerate(linhas)])
    conn.commit()


def pendentes_normalizacao(conn, ceasa):
    return [_data(r[0]) for r in conn.consultar(
        "SELECT data FROM boletim WHERE ceasa_id = %s AND status = 'ok' AND normalizado = FALSE ORDER BY data",
        (ceasa,))]


def linhas(conn, ceasa, data):
    """[(pagina, ordem, metodo, [celulas])] na ordem original."""
    out = []
    for pag, ordem, met, cel in conn.consultar(
            "SELECT pagina, ordem, metodo, celulas FROM linha_bruta WHERE ceasa_id = %s AND data = %s "
            "ORDER BY pagina, ordem", (ceasa, conn.d(data))):
        if isinstance(cel, str):
            cel = json.loads(cel)
        out.append((pag, ordem, met, ["" if c is None else str(c) for c in cel]))
    return out


def gravar_cotacoes(conn, ceasa, data, cotacoes):
    d = conn.d(data)
    conn.executar("DELETE FROM cotacao WHERE ceasa_id = %s AND data = %s", (ceasa, d))
    conn.varios(
        "INSERT INTO cotacao (ceasa_id, data, produto, detalhe, embalagem, minimo, comum, maximo, "
        "situacao, conferencia) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [(ceasa, d, c["produto"], c["detalhe"], c["embalagem"], c["minimo"], c["comum"], c["maximo"],
          c["situacao"], c["conferencia"]) for c in cotacoes])
    conn.executar("UPDATE boletim SET normalizado = TRUE WHERE ceasa_id = %s AND data = %s", (ceasa, d))
    conn.commit()


def renormalizar(conn, ceasa):
    """Marca todos os boletins para serem normalizados de novo (use depois de melhorar o parser)."""
    conn.executar("UPDATE boletim SET normalizado = FALSE WHERE ceasa_id = %s AND status = 'ok'", (ceasa,))
    conn.commit()


def cotacoes_validadas(conn):
    f = lambda v: None if v is None else float(v)
    return [(str(_data(r[0])), r[1], r[2], r[3], r[4], f(r[5]), f(r[6]), f(r[7]), r[8], r[9]) for r in conn.consultar(
        "SELECT data, ceasa_id, produto, detalhe, embalagem, minimo, comum, maximo, situacao, conferencia "
        "FROM cotacao WHERE conferencia = 'validado' ORDER BY data, ceasa_id, produto, detalhe")]


def rotulos(conn):
    return {r[0]: r[1] for r in conn.consultar("SELECT id, nome FROM ceasa ORDER BY id")}
