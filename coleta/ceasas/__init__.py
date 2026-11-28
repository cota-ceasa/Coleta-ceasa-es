"""Registro das CEASAs coletadas. Para adicionar uma: crie ceasas/xx.py e inclua aqui."""
from .ba import ColetorBA
from .es import ColetorES
from .pr import COLETORES_PR
from .prohort import InspecaoProhort
from .rj import ColetorRJ
from .rs import ColetorRS
from .sp import ColetorSP

REGISTRO = {c.id: c for c in (ColetorES(), ColetorBA(), ColetorRJ(), ColetorSP(), ColetorRS(), *COLETORES_PR)}
# só para --discover (ainda não coletam)
INSPECAO = {c.id: c for c in (InspecaoProhort(),)}
