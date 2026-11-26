"""Registro das CEASAs coletadas. Para adicionar uma: crie ceasas/xx.py e inclua aqui."""
from .ba import ColetorBA
from .es import ColetorES
from .prohort import InspecaoProhort
from .rj import ColetorRJ
from .sp import ColetorSP

REGISTRO = {c.id: c for c in (ColetorES(), ColetorBA(), ColetorRJ(), ColetorSP())}
# só para --discover (ainda não coletam)
INSPECAO = {c.id: c for c in (InspecaoProhort(),)}
