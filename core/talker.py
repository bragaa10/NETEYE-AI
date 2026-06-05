"""
NetEye — core/talker.py
========================
Regras simples:
  - Espera < 3s  → silêncio
  - Espera > 3s  → uma palavra só: "A abrir.", "Aguarda." — SÓ UMA VEZ
  - Para IMEDIATAMENTE quando há resposta
  - Não faz chamadas extra nem busca notícias/clima.
"""

import threading, random
from rich.console import Console
console = Console()

CURTAS = {
    "navegar":          ["A abrir."],
    "pesquisar_google": ["A pesquisar."],
    "clicar":           ["Aguarda."],
    "escrever":         ["Aguarda."],
    "pressionar_enter": ["Aguarda."],
    "voltar":           ["A voltar."],
    "default":          ["Um momento.", "Aguarda."],
}


class Talker:
    def __init__(self, falar_fn, api_key: str | None = None):
        self._falar    = falar_fn
        # api_key mantida na assinatura para retro-compatibilidade mas não usada
        self._parar    = threading.Event()
        self._thread   = None
        self._ativo    = False

    def iniciar_comando(self, acao: str = ""):
        if self._ativo:
            return
        self._ativo = True
        self._parar.clear()
        self._thread = threading.Thread(
            target=self._loop,
            args=(acao.lower(),),
            daemon=True
        )
        self._thread.start()

    def parar(self):
        self._ativo = False
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=0.3)
        self._thread = None

    def _loop(self, acao: str):
        # Fase 1: esperar 3s — se resposta chega antes, silêncio total
        if self._parar.wait(timeout=3.0):
            return

        # Frase curta — SÓ UMA VEZ
        chave = acao if acao in CURTAS else "default"
        frase = random.choice(CURTAS[chave])
        self._dizer(frase)

        # Não faz mais nada. Sem falas intermédias longas nem clima/notícias.
        return

    def _dizer(self, texto: str):
        if texto and not self._parar.is_set():
            try:
                self._falar(texto, nao_bloquear=True)
            except Exception:
                pass