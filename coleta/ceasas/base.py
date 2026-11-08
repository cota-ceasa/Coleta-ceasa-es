"""Contrato de um coletor de CEASA. Cada CEASA nova = um arquivo que herda de Coletor."""
import datetime as dt
import re


def parse_data(txt):
    """'dd/mm/aaaa' ou 'aaaa-mm-dd' -> date; None se não reconhecer."""
    txt = (txt or "").strip()
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if m:
        d, mth, y = map(int, m.groups())
        return dt.date(y, mth, d)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", txt)
    if m:
        y, mth, d = map(int, m.groups())
        return dt.date(y, mth, d)
    return None


class Coletor:
    id = ""     # sigla usada no app e no banco (ex.: 'ES')
    nome = ""   # rótulo exibido no app
    uf = ""

    def datas(self, page):
        """Lista [(date, ref)] dos boletins disponíveis. 'ref' é o que baixar() precisa."""
        raise NotImplementedError

    def baixar(self, page, ref):
        """Bytes do PDF do boletim, ou None se o site não tiver o arquivo."""
        raise NotImplementedError

    def capturar(self, page, ref):
        """Boletim de uma data: (bytes_brutos, extensão, linhas) ou None se não houver.
        linhas: [(pagina, ordem, metodo, [celulas])]. Cada CEASA implementa o seu."""
        raise NotImplementedError

    def normalizar(self, linhas, data):
        """Converte as linhas cruas do PDF em cotações padronizadas.

        linhas: [(pagina, ordem, metodo, [celulas])]
        Retorna lista de dicts com: produto, detalhe, embalagem, minimo, comum, maximo,
        situacao, conferencia ('validado' para ir ao app).
        Retorne None enquanto o parser não estiver pronto (os boletins ficam aguardando).
        """
        return None

    def discover(self, page, pasta):
        """Opcional: salva HTML/print da página para inspecionar o formulário."""
        raise NotImplementedError
