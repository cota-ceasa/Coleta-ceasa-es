"""Prohort/Conab — preços das unidades do INTERIOR da CEAGESP (e de outras CEASAs do país).

A página ceagesp.gov.br/cotacoes/interior/ não tem tabela própria: manda para um painel Pentaho
(CDF) da Conab. O painel busca os dados em chamadas /pentaho/plugin/cda/api/doQuery
(path=...cda, dataAccessId=..., paramXxx=...). Antes de escrever o coletor é preciso saber
essas chamadas, e o servidor não abre para inspeção de fora. Por isso, por ora, só inspeção:

    python -m coleta.run --discover PROHORT

Abre o painel, mexe em cada <select> que aparecer e grava em saida/prohort/:
  chamadas.json   todas as chamadas doQuery (URL, método, corpo) e o início de cada resposta
  painel.html / painel.png
Mande esses arquivos para eu montar o coletor das unidades (Ribeirão Preto, Campinas, Sorocaba,
São José do Rio Preto, Bauru, Marília, Presidente Prudente, Araçatuba, Franca, Guaratinguetá,
Piracicaba, São José dos Campos...).
"""
import json
import os

# link publicado pela própria CEAGESP (usuário/senha públicos de leitura do painel)
URL = os.environ.get(
    "PROHORT_URL",
    "https://pentahoportaldeinformacoes.conab.gov.br/pentaho/api/repos/%3Ahome%3APROHORT%3AprecoDia.wcdf/"
    "generatedContent?userid=pentaho&password=password")


class InspecaoProhort:
    id = "PROHORT"
    nome = "Prohort/Conab (inspeção)"
    uf = ""

    def discover(self, page, pasta):
        pasta = pasta / "prohort"
        pasta.mkdir(parents=True, exist_ok=True)
        chamadas = []

        def resposta(r):
            if "/cda/" not in r.url and "doQuery" not in r.url:
                return
            try:
                corpo = r.text()[:3000]
            except Exception as e:  # noqa: BLE001
                corpo = f"<sem corpo: {e}>"
            chamadas.append({"url": r.url, "metodo": r.request.method,
                             "post": r.request.post_data, "status": r.status, "resposta": corpo})

        page.on("response", resposta)
        page.goto(URL, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(5000)
        sels = page.locator("select")
        print(f"{sels.count()} selects no painel")
        for i in range(sels.count()):
            s = sels.nth(i)
            ops = [(o.get_attribute("value"), o.inner_text().strip()) for o in s.locator("option").all()]
            print(f"select #{i} id={s.get_attribute('id')} ({len(ops)} opções): {ops[:40]}")
            if len(ops) > 1:
                try:   # escolhe a 2ª opção para o painel disparar a consulta dependente
                    s.select_option(value=ops[1][0])
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(3000)
                except Exception as e:  # noqa: BLE001
                    print("   não deu para escolher:", e)
        (pasta / "painel.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(pasta / "painel.png"), full_page=True)
        (pasta / "chamadas.json").write_text(json.dumps(chamadas, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(chamadas)} chamadas CDA gravadas em {pasta}/chamadas.json")
        for c in chamadas[:30]:
            print(" ", c["metodo"], c["url"][:200], (c["post"] or "")[:200])
