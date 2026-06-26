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
    "navegar":          ["A abrir a página.", "A aceder ao site."],
    "pesquisar_google": ["A pesquisar no Google.", "A efetuar pesquisa."],
    "clicar":           ["A clicar no elemento.", "A clicar."],
    "escrever":         ["A escrever no campo.", "A introduzir texto."],
    "pressionar_enter": ["A enviar.", "A pressionar enter."],
    "ler_pagina":       ["A analisar o conteúdo da página.", "A ler a página."],
    "onde_estou":       ["A verificar a tua localização.", "A localizar."],
    "ler_ecra_ocr":     ["A efetuar leitura ótica do ecrã.", "A ler o ecrã."],
    "ajustar_voz":      ["A ajustar a voz.", "A alterar definições de voz."],
    "limpar_historico": ["A apagar o histórico."],
    "default":          ["Um momento.", "Por favor, aguarda."],
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
        # Se for default (Claude API request), aguardamos 2s antes de dizer "A processar."
        if acao == "default":
            if self._parar.wait(timeout=2.0):
                return
            
            self._dizer("A processar.")
            
            # Se demorar mais 3 segundos (5 segundos total), dar uma das frases default
            if self._parar.wait(timeout=3.0):
                return
            
            frase = random.choice(CURTAS["default"])
            self._dizer(frase)
        else:
            # Se for uma ferramenta específica (tool-context message)
            # Dizemos imediatamente a mensagem de contexto
            chave = acao if acao in CURTAS else "default"
            frase = random.choice(CURTAS[chave])
            self._dizer(frase)
            
            # Se a ferramenta demorar mais de 2.5 segundos a executar, dizemos "A processar..."
            if self._parar.wait(timeout=2.5):
                return
            
            self._dizer("A processar.")
        
        return

    def _dizer(self, texto: str):
        if texto and not self._parar.is_set():
            try:
                self._falar(texto, nao_bloquear=True)
            except Exception:
                pass