"""Registro das CEASAs coletadas. Para adicionar uma: crie ceasas/xx.py e inclua aqui."""
from .ba import ColetorBA
from .es import ColetorES
from .rj import ColetorRJ

REGISTRO = {c.id: c for c in (ColetorES(), ColetorBA(), ColetorRJ())}
