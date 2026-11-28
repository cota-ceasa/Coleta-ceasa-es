# Instruções para o Claude

## Autorizações permanentes do dono do repositório
- Pode fazer **merge** dos PRs que abrir neste repositório (squash) sem pedir confirmação.
- Depois do merge de mudanças no app (`docs/`), pode rodar o workflow **"Publicar só o app (sem coletar)"** (`.github/workflows/publicar-app.yml`) no `main`.
- Se algo der errado, reverter abrindo um PR que desfaz o commit.

## Preferências
- Respostas curtas e objetivas, em português.
- Ao mudar arquivos do app, aumentar a versão de `CACHE_NAME` em `docs/sw.js`.
