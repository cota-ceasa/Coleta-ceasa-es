-- Tabelas da coleta: criadas sozinhas na primeira execução (Postgres ou SQLite).
CREATE TABLE IF NOT EXISTS ceasa (
    id   TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    uf   TEXT
);

-- um registro por CEASA e dia de boletim
CREATE TABLE IF NOT EXISTS boletim (
    ceasa        TEXT NOT NULL,
    data         TEXT NOT NULL,              -- AAAA-MM-DD
    status       TEXT NOT NULL,              -- ok | sem_dados | erro
    hash         TEXT,
    erro         TEXT,
    normalizado  INTEGER NOT NULL DEFAULT 0, -- 0 = linhas brutas ainda por normalizar
    atualizado   TEXT NOT NULL,
    PRIMARY KEY (ceasa, data)
);

-- linhas exatamente como vieram do site (permite reprocessar sem baixar de novo)
CREATE TABLE IF NOT EXISTS linha_bruta (
    ceasa   TEXT NOT NULL,
    data    TEXT NOT NULL,
    ordem   INTEGER NOT NULL,
    pagina  INTEGER,
    metodo  TEXT,
    celulas TEXT NOT NULL,                   -- lista JSON de células
    PRIMARY KEY (ceasa, data, ordem)
);

-- cotações padronizadas; só 'validado' vai para o app
CREATE TABLE IF NOT EXISTS cotacao (
    ceasa        TEXT NOT NULL,
    data         TEXT NOT NULL,
    ordem        INTEGER NOT NULL,
    produto      TEXT NOT NULL,
    detalhe      TEXT NOT NULL,
    embalagem    TEXT NOT NULL,
    minimo       DOUBLE PRECISION,
    comum        DOUBLE PRECISION NOT NULL,
    maximo       DOUBLE PRECISION,
    situacao     TEXT,
    conferencia  TEXT NOT NULL,
    PRIMARY KEY (ceasa, data, ordem)
);
