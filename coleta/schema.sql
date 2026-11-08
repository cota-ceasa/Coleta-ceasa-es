-- Tabelas da coleta. Mesmo formato das tabelas que já existem no seu banco Neon:
-- se elas já existem, nada muda. Num banco novo (ou no SQLite local) são criadas aqui.
CREATE TABLE IF NOT EXISTS ceasa (
    id     TEXT PRIMARY KEY,
    nome   TEXT NOT NULL,
    uf     TEXT,
    ativo  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS boletim (
    ceasa_id     TEXT NOT NULL,
    data         DATE NOT NULL,
    status       TEXT NOT NULL,
    pdf_sha256   TEXT,
    erro         TEXT,
    tentativas   INTEGER NOT NULL DEFAULT 0,
    normalizado  BOOLEAN NOT NULL DEFAULT FALSE,
    coletado_em  TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (ceasa_id, data)
);

CREATE TABLE IF NOT EXISTS linha_bruta (
    ceasa_id  TEXT NOT NULL,
    data      DATE NOT NULL,
    pagina    INTEGER,
    ordem     INTEGER NOT NULL,
    metodo    TEXT,
    celulas   TEXT NOT NULL,
    PRIMARY KEY (ceasa_id, data, ordem)
);

CREATE TABLE IF NOT EXISTS cotacao (
    ceasa_id     TEXT NOT NULL,
    data         DATE NOT NULL,
    produto      TEXT NOT NULL,
    detalhe      TEXT NOT NULL,
    embalagem    TEXT NOT NULL,
    minimo       NUMERIC,
    comum        NUMERIC NOT NULL,
    maximo       NUMERIC,
    situacao     TEXT,
    conferencia  TEXT NOT NULL
);
