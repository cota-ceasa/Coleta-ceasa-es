# COTA CEA$A — app + coleta automática (CEASA-ES)

```
docs/                    app (PWA), publicado no GitHub Pages
coleta/run.py            baixar boletins -> banco -> padronizar -> docs/dados.json
coleta/ceasas/es.py      coletor da CEASA-ES (lê a tabela HTML do boletim)
coleta/ceasas/ba.py      coletor da CEASA-BA/Salvador (baixa os PDFs listados no portal da SDE)
coleta/ceasas/rj.py      coletor da CEASA-RJ (Cotação -> ano -> mês -> PDF do dia)
coleta/ceasas/sp.py      coletor da CEAGESP capital (formulário de cotações, todas as categorias por data)
coleta/ceasas/prohort.py inspeção do painel Prohort/Conab (unidades do interior da CEAGESP)
coleta/db.py             banco (Postgres via DATABASE_URL, ou SQLite local sem configurar nada)
coleta/exportar.py       banco -> dados.json
coleta/schema.sql        tabelas (criadas sozinhas)
.github/workflows/       agendamento e botão "Run workflow"
```

## Configurar no GitHub (uma vez, ~10 min)

1. **Banco grátis**: crie um projeto no [Neon](https://neon.tech) e copie a *connection string*
   (`postgresql://...?sslmode=require`). As tabelas são criadas sozinhas.
2. **Repositório**: crie um repositório **público** e envie todo o conteúdo desta pasta
   (incluindo a pasta oculta `.github`).
3. **Segredo**: Settings → Secrets and variables → Actions → *New repository secret*:
   nome `DATABASE_URL`, valor = a connection string.
4. **Pages**: Settings → Pages → Source: **GitHub Actions**.

## Primeira execução

1. Actions → **Coleta CEASA** → *Run workflow* com `discover = ES`.
   Baixe o artefato **saida** e confira `pagina.png` (o formulário apareceu? as datas foram listadas?).
2. Carga de vários dias: *Run workflow* com `inicio = 2026-08-24` e `max = 60`.
   Cada execução baixa até `max` boletins ainda não coletados (o log diz quantos faltam).
   **Repita até o log mostrar "0 boletins pendentes".** O que já foi coletado não é baixado de novo.
3. Depois disso o agendamento (seg–sáb, 12:17 e 18:47) busca só os boletins novos.
   O app é republicado a cada execução.

## Como funciona a conferência

- Linhas com número ou embalagem inválidos, mín > comum > máx, ou data do boletim diferente da
  pedida ficam no banco como `revisar` e **não vão para o app**; o log mostra quais.
- Produto que o app ainda não conhece **não é descartado**: aparece em "Outros" e o log lista
  `produtos novos`. Para dar o grupo certo, inclua o nome em `GRUPOS` (`coleta/gerar_dados.py`)
  e rode o workflow com `renormalizar` marcado (refaz tudo a partir das linhas guardadas, sem
  baixar de novo).
- Linha repetida no mesmo boletim (ex.: UVA RED GLOBE duas vezes): a 2ª aparece com " (2)".
- Embalagens novas (`CX 20 DZ`, `SC 25 KG`...) são reconhecidas pelo texto.

## Rodar no seu computador

```bash
pip install -r requirements.txt && python -m playwright install chromium
python -m coleta.run --ceasa ES --inicio 2026-10-01 --headed   # sem DATABASE_URL usa o arquivo coleta.db
python -m http.server -d docs 8000                              # app em http://localhost:8000
```

## CEAGESP (São Paulo)

- **Capital** (`SP`): coleta Frutas, Legumes, Verduras, Diversos, Pescados e Orgânicos de cada data
  publicada (seg, qua e sex). O site só lista os boletins recentes, por isso não há carga histórica longa.
  Flores ficam de fora; para incluir, defina `CEAGESP_GRUPOS="DIVERSOS,FLORES,FRUTAS,LEGUMES,ORGÂNICOS,PESCADOS,VERDURAS"`.
  Teste: *Run workflow* com `discover = SP` e confira `sp_resultado.html` no artefato.
- **Interior** (Ribeirão Preto, Campinas, Sorocaba etc.): a CEAGESP publica no painel Prohort da Conab.
  Rode *Run workflow* com `discover = PROHORT` e envie `saida/prohort/chamadas.json` para montar o coletor.

## Adicionar outra CEASA

Crie `coleta/ceasas/xx.py` herdando de `Coletor` (`datas()`, `capturar()`, `normalizar()`; veja `es.py`)
e registre em `coleta/ceasas/__init__.py`. Ela aparece sozinha no seletor de localidade do app.

## Se der erro

- `formulário mudou` / `a lista de datas não carregou`: rode `discover` e confira `pagina.png`.
- `3 erros seguidos`: o site provavelmente está fora do ar; a próxima execução continua de onde parou.
- Site recusando o servidor do GitHub: rode no seu computador com `--headed` (mesmo comando acima),
  apontando `DATABASE_URL` para o mesmo banco.

## Runner no seu computador (CEASA-RJ)

O portal rj.gov.br bloqueia os servidores do GitHub. O Rio é coletado pelo workflow
**Coleta CEASA (computador local)**, que roda num *self-hosted runner* no seu PC
(seg–sáb, 12:02 e 18:32; o app é publicado pela coleta da nuvem 15 min depois).

1. GitHub → Settings → Actions → Runners → **New self-hosted runner** → escolha o sistema
   e rode os comandos mostrados (download + `config`). No `config`, quando pedir
   *labels*, digite `ceasa-local`.
2. Deixe rodando como serviço: Windows `./svc.cmd install` e `./svc.cmd start`
   (ou rode `run.cmd` / `./run.sh` numa janela). O PC precisa estar ligado nos horários.
3. Teste: Actions → **Coleta CEASA (computador local)** → *Run workflow* com `inicio`.

Segurança (repositório público): Settings → Actions → General → *Fork pull request
workflows* → **Require approval for all outside collaborators**. Os workflows deste projeto
não rodam em pull requests, então código de terceiros não executa no seu PC.
