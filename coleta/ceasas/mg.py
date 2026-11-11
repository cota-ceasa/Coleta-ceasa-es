"""CEASA-MG (CeasaMinas) — 7 unidades no mesmo sistema do ES (Scriptcase).

Formulário (mobile): https://minas1.ceasa.mg.gov.br/detec/filtro_boletim/filtro_boletim_mob.php
  select #id_sc_field_mercado, select #id_sc_field_datas, botão "Pesquisar Boletim".
Boletim: boletim_completo.php, a mesma grade do ES (prdnom, embdesresu, pboprcmin, pboprccomum,
pboprcmax, mersit). Cada unidade vira uma "CEASA" própria no app e no banco.
Se o site mudar, rode:  python -m coleta.run --discover BH
"""
import os

from .es import ColetorES

URL_MG = os.environ.get("CEASA_MG_URL", "https://minas1.ceasa.mg.gov.br/detec/filtro_boletim/filtro_boletim_mob.php")

# id no app, nome exibido, código do mercado no site, sigla (texto da opção), trechos do cabeçalho "Mercado:"
UNIDADES = [
    ("BH",  "CEASA - Grande BH (MG)",       "214", "CEAMG", ("GRANDE BH", "CONTAGEM")),
    ("JF",  "CEASA - Juiz de Fora (MG)",    "217", "CEARM", ("JUIZ DE FORA",)),
    ("UDI", "CEASA - Uberlândia (MG)",      "218", "CEART", ("UBERLANDIA",)),
    ("CAR", "CEASA - Caratinga (MG)",       "237", "CECAT", ("CARATINGA",)),
    ("GV",  "CEASA - Gov. Valadares (MG)",  "260", "CEARD", ("VALADARES",)),
    ("BAR", "CEASA - Barbacena (MG)",       "353", "CEARB", ("BARBACENA",)),
    ("UBA", "CEASA - Uberaba (MG)",         "215", "CEARG", ("UBERABA",)),
]
_TODOS = [c for _i, _n, _v, _s, chaves in UNIDADES for c in chaves]


def _criar(id_, nome, valor, sigla, chaves):
    return type(f"ColetorMG_{id_}", (ColetorES,), {
        "id": id_, "nome": nome, "uf": "MG", "url": URL_MG,
        "mercado_valor": valor, "mercado_chave": sigla,
        "cabecalho_chaves": chaves,
        "outros_mercados": tuple(c for c in _TODOS if c not in chaves),
        "apelidos": {},
    })()


COLETORES_MG = [_criar(*u) for u in UNIDADES]
