"""Padronização compartilhada por todas as CEASAs: nome do produto, números e situação.

Cada CEASA escreve seus nomes de um jeito ("BROCOLO NINJA", "ALHO PORRO"...). Aqui eles viram o
"Produto padrão" de GRUPOS (gerar_dados.py) + detalhe. Diferenças de grafia ficam num dicionário
de apelidos por CEASA, sem mexer na lógica.
"""
import re
import unicodedata

from .gerar_dados import GRUPO_DE, emb_info

SITUACAO = {"ME": "estável", "MFI": "firme", "MFR": "fraco"}

# Apelidos válidos para qualquer CEASA (nome normalizado -> produto padrão)
APELIDOS_GERAIS = {
    "AIPIM": "Aipim / Mandioca",
    "MANDIOCA": "Aipim / Mandioca",
    "MACAXEIRA": "Aipim / Mandioca",
    "BROCOLO": "Brócolis",
    "BROCOLOS": "Brócolis",
    "BROCOLIS": "Brócolis",
    "ALHO PORRO": "Alho-poró",
    "ALHO PORO": "Alho-poró",
    "MAMAO HAWAY": "Mamão Havaí",
    "MAMAO HAVAI": "Mamão Havaí",
    "MAMAO PAPAYA": "Mamão Havaí",
    "UVA PASSAS": "Uva Passa",
    "OVOS CODORNA": "Ovos de Codorna",
    "OVO CODORNA": "Ovos de Codorna",
    "LIMA PERSIA": "Lima da Pérsia",
    "FAR MANDIOCA": "Farinha de Mandioca",
    "FAR DE MANDIOCA": "Farinha de Mandioca",
    "FARINHA MANDIOCA": "Farinha de Mandioca",
    "FEIJAO CARIOQUINHA": "Feijão Carioca",
    "FEIJAO CARIOCA": "Feijão Carioca",
    "PHISALIS": "Physalis",
    "FISALIS": "Physalis",
    "CACAO": "Cacau",
    "UVA": "Uva (outras)",  # só vale quando nenhuma uva específica casar (Itália, Niágara, Passa)
}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    """'Couve-flor' -> 'COUVE FLOR'; 'CAT. 1 T. 135-150' -> 'CAT 1 T 135 150'."""
    s = sem_acento(str(s)).upper()
    s = re.sub(r"[./\-()]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _indice(apelidos):
    idx = {norm(p): p for p in GRUPO_DE}
    idx.update({norm(k): v for k, v in apelidos.items()})
    # mais palavras primeiro: "COUVE FLOR" antes de "COUVE", "BANANA MACA" antes de "MACA"
    return sorted(idx.items(), key=lambda kv: -len(kv[0].split()))


_CACHE = {}


def produto_detalhe(descricao, apelidos=None):
    """Retorna (produto padrão, detalhe) ou (None, descrição) se não reconhecer."""
    chave = id(apelidos)
    if chave not in _CACHE:
        _CACHE[chave] = _indice({**APELIDOS_GERAIS, **(apelidos or {})})
    palavras = norm(descricao).split()
    for nome, produto in _CACHE[chave]:
        n = nome.split()
        if palavras[:len(n)] == n:
            return produto, " ".join(palavras[len(n):])
    return None, ""


def nome_novo(descricao):
    """'BACALHAU SECO' -> 'Bacalhau Seco' (nome de produto ainda não cadastrado)."""
    return " ".join(w.capitalize() for w in re.sub(r"\s+", " ", str(descricao)).strip().split())


def numero(txt):
    """'1.234,56' -> 1234.56; None se vazio ou inválido."""
    txt = (txt or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def cotacao(descricao, embalagem, mn, com, mx, sit, apelidos=None, data_ok=True):
    """Monta o dict de cotação com conferência automática. None se não for linha de preço."""
    com = numero(com)
    if com is None:
        return None
    mn, mx = numero(mn), numero(mx)
    produto, detalhe = produto_detalhe(descricao, apelidos)
    emb = re.sub(r"\s+", " ", (embalagem or "").strip().upper())
    # Produto que o app ainda não conhece NÃO é descartado: entra com o nome do boletim
    # (em "Outros"), desde que os números e a embalagem façam sentido. O log avisa para
    # você decidir se vale cadastrar o nome em GRUPOS.
    ok = (data_ok and emb_info(emb) is not None and com > 0
          and (mn is None or mn <= com) and (mx is None or com <= mx))
    return {
        "produto": produto or nome_novo(descricao),
        "detalhe": detalhe,
        "embalagem": emb,
        "minimo": mn, "comum": com, "maximo": mx,
        "situacao": SITUACAO.get((sit or "").strip().upper()),
        "conferencia": "validado" if ok else "revisar",
    }
