"""CEASA-ES (Ceasa Grande Vitória) — formulário Scriptcase com o boletim numa grade HTML.

Formulário: select #id_sc_field_mercado (Grande Vitória = 211) e #id_sc_field_datas, botão Ok.
Ao escolher o mercado (e às vezes a data) o site RECARREGA a página; por isso cada leitura
espera a página assentar e tolera o "Execution context was destroyed" da recarga.
Depois do Ok, a página boletim_completo_es.php mostra a grade com campos identificados
(prdnom, embdesresu, pboprcmin, pboprccomum, pboprcmax, mersit): lemos direto do HTML.
Se o site mudar, rode:  python -m coleta.run --discover ES
"""
import os
import re
from html import unescape

from ..padronizar import cotacao, numero, produto_detalhe
from .base import Coletor, parse_data

URL = os.environ.get("CEASA_ES_URL", "http://200.198.51.71/detec/filtro_boletim_es/filtro_boletim_es.php")
SEL_MERCADO = "#id_sc_field_mercado"
SEL_DATAS = "#id_sc_field_datas"
MERCADO_ID = "211"  # CEASA GRANDE VITÓRIA
# grafias do boletim do ES que diferem do nome padrão (o resto casa sozinho)
APELIDOS = {"MISTURA": "Mistura de Peixes"}  # no ES, "MISTURA" é peixe misto
LINHA = re.compile(r"^(.+?)\s+(CX \d+ DZ|ENG \d+ UNID|UN \d+,\d+ KG|UN|KG)\s+"
                   r"([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)(?:\s+(M[A-Z]{1,2}))?$")
# ids dos campos na grade do boletim (Scriptcase): id_sc_field_<campo>_<n>
CAMPOS = ["id_sc_field_prdnom_", "id_sc_field_embdesresu_", "id_sc_field_pboprcmin_",
          "id_sc_field_pboprccomum_", "id_sc_field_pboprcmax_", "id_sc_field_mersit_"]
BTN_OK = ["#sc_b_ok_t", "#sc_b_ok_b", "a:has-text('Ok')", "text=Ok"]


class ColetorES(Coletor):
    id = "ES"
    nome = "CEASA - Vitória (ES)"
    uf = "ES"

    @staticmethod
    def _contar(page, seletor, tentativas=60, minimo=2):
        """Espera o select ter ao menos 'minimo' opções, atravessando recargas da página."""
        for _ in range(tentativas):
            try:
                page.wait_for_load_state("domcontentloaded")
                if page.locator(f"{seletor} option").count() >= minimo:
                    return True
            except Exception:  # noqa: BLE001 (página recarregando no meio da leitura)
                pass
            page.wait_for_timeout(500)
        return False

    def _abrir(self, page):
        page.goto(URL, wait_until="networkidle", timeout=60000)
        if not self._contar(page, SEL_MERCADO):
            raise RuntimeError("formulário mudou: select de mercado não encontrado (rode --discover ES)")
        valor = MERCADO_ID
        for o in page.locator(f"{SEL_MERCADO} option").all():  # confirma pelo nome, se o código mudar
            if "GRANDE VIT" in o.inner_text().upper():
                valor = o.get_attribute("value")
        page.select_option(SEL_MERCADO, value=valor)   # dispara a recarga
        page.wait_for_timeout(1000)
        if not self._contar(page, SEL_DATAS):
            raise RuntimeError("a lista de datas não carregou depois de escolher o mercado")
        page.wait_for_load_state("networkidle")
        return page.locator(SEL_DATAS)

    def datas(self, page):
        dsel = self._abrir(page)
        for tentativa in range(3):  # se a página ainda recarregar durante a leitura, lê de novo
            try:
                out = set()
                for o in dsel.locator("option").all():
                    ref = o.get_attribute("value")
                    d = parse_data(o.inner_text()) or parse_data(ref)
                    if d:
                        out.add((d, ref))
                return sorted(out)
            except Exception:  # noqa: BLE001
                if tentativa == 2:
                    raise
                page.wait_for_timeout(1500)

    def capturar(self, page, ref):
        """Abre o boletim da data e lê a tabela direto do HTML (não precisa gerar PDF).
        Retorna (html_bytes, 'html', linhas) ou None se o site não trouxer o boletim."""
        self._abrir(page)
        page.select_option(SEL_DATAS, value=ref)   # pode recarregar a página também
        page.wait_for_timeout(1000)
        page.wait_for_load_state("networkidle")
        for s in BTN_OK:
            loc = page.locator(s)
            if loc.count():
                loc.first.click()
                break
        else:
            raise RuntimeError("botão Ok não encontrado")
        try:
            html = self._esperar_grade(page.context)
            if html is not None:
                html = self._todas_as_paginas(page.context, html)
        finally:
            for p in page.context.pages[1:]:  # fecha abas extras, se o site abrir alguma
                p.close()
        if html is None:
            return None
        linhas = linhas_do_html(html)
        if not any(len(c) == 6 for *_x, c in linhas):
            return None  # página sem linhas de preço (ex.: "registros não encontrados")
        return html.encode("utf-8"), "html", linhas

    @staticmethod
    def _grade_page(ctx):
        for p in ctx.pages:
            try:
                if p.locator(f"[id^='{CAMPOS[0]}']").count():
                    return p
            except Exception:  # noqa: BLE001
                pass
        return None

    def _todas_as_paginas(self, ctx, html, limite=60):
        """A grade (Scriptcase) pode vir paginada. Aumenta as linhas por página, se houver o seletor,
        e segue em 'avançar' até acabar, juntando o HTML das páginas. Sem paginação = 1 página."""
        p = self._grade_page(ctx)
        if p is None:
            return html
        try:  # tenta mostrar o máximo de linhas por página
            for sel in ("select[name^='nmgp_quant_linhas']", "select[id^='quant_linhas']"):
                s = p.locator(sel)
                if s.count():
                    ops = [o.get_attribute("value") for o in s.first.locator("option").all()]
                    ops = [o for o in ops if o and o.isdigit()]
                    if ops:
                        s.first.select_option(value=max(ops, key=int))
                        p.wait_for_load_state("networkidle")
                        p.wait_for_timeout(800)
                        html = p.content()
                    break
        except Exception:  # noqa: BLE001
            pass
        partes, vistas = [html], {_assinatura(html)}
        for _ in range(limite):
            prox = p.locator("[id^='forward_']:not(.disabled), a[id^='forward_']")
            prox = [prox.nth(i) for i in range(prox.count()) if prox.nth(i).is_visible()]
            if not prox:
                break
            try:
                prox[0].click()
                p.wait_for_load_state("networkidle")
                p.wait_for_timeout(800)
                h = p.content()
            except Exception:  # noqa: BLE001
                break
            a = _assinatura(h)
            if a in vistas:  # voltou para uma página já lida (último botão ainda clicável)
                break
            vistas.add(a)
            partes.append(h)
        if len(partes) > 1:
            print(f"[ES] boletim em {len(partes)} páginas")
        return "\n".join(partes)

    @staticmethod
    def _esperar_grade(ctx, segundos=40):
        """Espera a grade do boletim aparecer (na mesma aba ou numa nova) e devolve o HTML."""
        for _ in range(segundos * 2):
            for p in ctx.pages:
                try:
                    if p.locator(f"[id^='{CAMPOS[0]}']").count():
                        p.wait_for_load_state("networkidle")
                        return p.content()
                    if re.search(r"n[ãa]o (foram )?encontrad", p.locator("body").inner_text(), re.I):
                        return None
                except Exception:  # noqa: BLE001 (página carregando)
                    pass
            ctx.pages[0].wait_for_timeout(500)
        raise RuntimeError("a tabela do boletim não apareceu em 40 s")

    def normalizar(self, linhas, data):
        """Tabela do boletim: DESCRIÇÃO | EMBALAGEM | MÍN | COMUM | MÁX | SITUAÇÃO (ME/MFI/MFR).
        A 1ª linha traz 'Data Pesquisada: dd/mm/aaaa', usada para conferir o dia do boletim."""
        data_pdf = None
        out, ignoradas = [], []
        for _pag, _ordem, _metodo, cel in linhas:
            texto = " ".join(c for c in cel if c)
            if "Data Pesquisada" in texto:
                data_pdf = parse_data(texto.split("Data Pesquisada", 1)[1])
                continue
            partes = self._colunas(cel)
            if not partes:
                if texto.strip() and not texto.strip().isdigit():
                    ignoradas.append(texto)
                continue
            c = cotacao(*partes, apelidos=APELIDOS, data_ok=data_pdf in (None, data))
            if c:
                out.append(c)
        # Mesma linha repetida no boletim (ex.: "UVA RED GLOBE" nacional e importada, sem rótulo):
        # a 2ª ganha " (2)" no detalhe. Sem isso o app gravava só uma das duas.
        vistas = {}
        for c in out:
            k = (c["produto"], c["detalhe"], c["embalagem"])
            vistas[k] = vistas.get(k, 0) + 1
            if vistas[k] > 1:
                c["detalhe"] = f"{c['detalhe']} ({vistas[k]})".strip()
        novos = sorted({c["produto"] for c in out if produto_detalhe(c["produto"], APELIDOS)[0] is None})
        if novos:
            print(f"[ES] {data}: produtos novos (entram em 'Outros'; cadastre em GRUPOS): {novos}")
        if data_pdf and data_pdf != data:
            print(f"[ES] atenção: boletim pedido para {data}, PDF diz {data_pdf} (linhas ficam 'revisar')")
        revisar = sorted({f"{c['produto']} {c['detalhe']} [{c['embalagem']}]".strip()
                          for c in out if c["conferencia"] != "validado"})
        if revisar or ignoradas:
            fora = revisar + ignoradas
            print(f"[ES] {data}: {len(out) - len(revisar)} validadas; {len(fora)} fora do app: "
                  f"{fora[:10]}{' ...' if len(fora) > 10 else ''}")
        return out

    @staticmethod
    def _colunas(cel):
        """6 células já separadas, ou texto corrido (fallback) separado por regex."""
        cel = [c.strip() for c in cel]
        if len(cel) >= 5 and numero(cel[3]) is not None:
            return (cel + [""])[:6]
        m = LINHA.match(" ".join(c for c in cel if c))
        return m.groups() if m else None

    def discover(self, page, pasta):
        page.goto(URL, wait_until="networkidle", timeout=60000)
        (pasta / "pagina_inicial.html").write_text(page.content(), encoding="utf-8")
        for i in range(page.locator("select").count()):
            s = page.locator("select").nth(i)
            print(f"select #{i} id={s.get_attribute('id')} name={s.get_attribute('name')}")
            for o in s.locator("option").all()[:15]:
                print("   ", repr(o.get_attribute("value")), "|", o.inner_text().strip())
        try:
            datas = self.datas(page)
            print(f"\n{len(datas)} datas após escolher o mercado. Primeiras/últimas:",
                  datas[:3], "...", datas[-3:])
        except Exception as e:  # noqa: BLE001
            print("Falha ao carregar datas:", e)
        page.screenshot(path=str(pasta / "pagina.png"), full_page=True)
        print(f"Salvei {pasta}/pagina_inicial.html e pagina.png")


def linhas_do_html(html):
    """Grade do boletim -> [(pagina, ordem, metodo, celulas)], no mesmo formato da extração de PDF.
    A 1ª linha é o cabeçalho 'Data Pesquisada: dd/mm/aaaa' (usado para conferir a data)."""
    texto = lambda x: re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", x))).strip()
    out = []
    m = re.search(r"Data Pesquisada:?\s*[^<]*", html)
    if m:
        out.append((1, 0, "html", [texto(m.group(0))]))
    # Percorre os <tr> da grade (e não só os ids numerados): se o site repetir ou reiniciar a
    # numeração entre páginas, nenhuma linha se perde nem se sobrescreve.
    esperadas = len(re.findall(r'id="SC_ancor\d+"', html))
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S):
        achados = {campo: texto(v) for campo, v in
                   re.findall(r'id="(id_sc_field_[a-z]+_)\d+"[^>]*>(.*?)</span>', tr, re.S) if campo in CAMPOS}
        if CAMPOS[0] in achados:
            out.append((1, len(out), "html", [achados.get(c, "") for c in CAMPOS]))
    lidas = len(out) - (1 if m else 0)
    if esperadas and lidas != esperadas:
        print(f"[ES] atenção: a página tem {esperadas} linhas de preço e li {lidas}")
    return out


def _assinatura(html):
    """Identifica o conteúdo da grade (para saber se uma página é nova)."""
    return hash(tuple(re.findall(r'id="id_sc_field_prdnom_\d+"[^>]*>(.*?)</span>', html, re.S)))
