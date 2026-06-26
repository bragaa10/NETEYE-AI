"""
NetEye — core/assistant.py (INTELIGÊNCIA SÉNIOR)
================================================
Gere a lógica de interação, ferramentas e memória.
- [NOVO] Histórico de comandos e caching (Func 2 & 10)
- [NOVO] Confirmação de ações destrutivas (Func 3)
- [NOVO] Resolução de atalhos de voz (Func 6)
- [NOVO] Ferramentas de Acessibilidade (Func 4, 8, 9)
"""

import os
import json
import time
import anthropic
from rich.console import Console

console = Console()

class Assistant:
    def __init__(self, config: dict, api_key: str = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.config = config
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None
        
        self.talker_ativo = config.get("assistente", {}).get("talker_ativo", True)
        self._cb = {}
        self._talker = None
        self._get_screenshot = None
        self._falar_cb = None
        
        # Cache de respostas (Func 10)
        self._cache = {} # {comando_limpo: (resposta_texto, acao_nome, params)}
        self._cache_expiry = 1800 # 30 min
        self._last_url = ""
        
        # Estado de Confirmação (Func 3)
        self._pendente_confirmacao = None # (acao, params, msg_pergunta)
        
        # Atalhos (Func 6)
        self._atalhos = {} # {frase: acao}

    # ------------------------------------------------------------------
    # CONFIGURAÇÃO DE CALLBACKS
    # ------------------------------------------------------------------

    def registar_ferramenta(self, nome: str, func):
        self._cb[nome] = func

    def registar_falar(self, func):
        self._falar_cb = func
        # Inicializar o Talker quando tivermos o callback de falar
        if getattr(self, "talker_ativo", True) and not self._talker:
            try:
                from core.talker import Talker
                self._talker = Talker(func, self.api_key)
            except Exception as e:
                console.print(f"[red]Erro ao inicializar Talker: {e}[/red]")

    def registar_screenshot(self, func):
        self._get_screenshot = func

    def atualizar_atalhos(self, lista_atalhos: list):
        """Atualiza o dicionário de atalhos locais."""
        self._atalhos = {a["frase"].lower().strip(): a["acao"] for a in lista_atalhos}

    # ------------------------------------------------------------------
    # PROCESSAMENTO PRINCIPAL
    # ------------------------------------------------------------------

    def processar(self, comando: str, user_id: int = 1):
        """Processa um comando de voz com lógica sénior."""
        cmd_limpo = comando.lower().strip()
        
        # 1. Verificar Estado de Confirmação (Func 3)
        if self._pendente_confirmacao:
            if "sim" in cmd_limpo or "pode ser" in cmd_limpo or "confirmo" in cmd_limpo:
                acao, params, _ = self._pendente_confirmacao
                self._pendente_confirmacao = None
                res = self._exec(acao, params)
                msg = f"Ação confirmada e executada. {res.get('ok', '')}"
                self._falar(msg)
                # Registar na DB
                if "registar_comando" in self._cb: self._cb["registar_comando"](user_id, comando, msg)
                return
            elif "não" in cmd_limpo or "cancela" in cmd_limpo:
                self._pendente_confirmacao = None
                self._falar("Está bem, cancelei a ação.")
                return
            else:
                self._falar("Não entendi. Diz 'sim' para confirmar ou 'não' para cancelar.")
                return

        # 2. Verificar Atalhos Personalizados (Func 6)
        if cmd_limpo in self._atalhos:
            acao = self._atalhos[cmd_limpo]
            console.print(f"[bold blue]⚡ Atalho detetado: {cmd_limpo} -> {acao}[/bold blue]")
            res = self._exec_shortcut(acao)
            msg = f"A executar atalho para {cmd_limpo}."
            self._falar(msg)
            if "registar_comando" in self._cb: self._cb["registar_comando"](user_id, comando, msg)
            return

        # 3. Verificar Cache (Func 10)
        # Primeiro tentar o cache_manager (otimização) se disponível
        cache_manager = getattr(self, "_cache_manager", None)
        if cache_manager:
            cached = cache_manager.obter_comando_cache(cmd_limpo)
            if cached:
                console.print("[dim green]🚀 Cache hit (CacheManager)![/dim green]")
                resp = cached.get("resposta")
                acao = cached.get("acao")
                params = cached.get("params")
                if acao: self._exec(acao, params)
                if resp: self._falar(resp)
                return
        elif cmd_limpo in self._cache:
            resp, acao, params, timestamp = self._cache[cmd_limpo]
            if time.time() - timestamp < self._cache_expiry:
                console.print("[dim green]🚀 Cache hit (Memória Local)![/dim green]")
                if acao: self._exec(acao, params)
                self._falar(resp)
                return

        # 4. Processamento Claude (Tool Use)
        hist = [{"role":"user","content":comando}]
        try:
            # Enviar para o loop de iterações do Claude
            resposta_final = self._loop_claude(hist, user_id)
            
            # Se for um comando simples (sem parâmetros complexos), guardar em cache
            if len(comando.split()) < 4:
                if cache_manager:
                    cache_manager.cache_comando(cmd_limpo, {"resposta": resposta_final, "acao": None, "params": None})
                else:
                    self._cache[cmd_limpo] = (resposta_final, None, None, time.time())
                
            if "registar_comando" in self._cb: 
                self._cb["registar_comando"](user_id, comando, resposta_final)
                
        except Exception as e:
            console.print(f"[red]Erro Assistant: {e}[/red]")
            self._falar("Desculpa, tive um erro ao processar o teu pedido.")

    def _loop_claude(self, hist: list, user_id: int) -> str:
        # Instruções de Sistema (Persona Sénior)
        system_prompt = (
            "És o NetEye, um assistente de voz para navegação web concebido para utilizadores invisuais. "
            "Fala de forma natural, calorosa e coloquial, como numa conversa normal. "
            "Responde sempre de forma extremamente concisa, com no máximo duas frases curtas. "
            "Nunca uses listas, marcadores, bullets, asteriscos ou formatação markdown, pois a tua resposta será lida por um sintetizador de voz. "
            "Não descrevas os passos técnicos que fizeste; diz diretamente o resultado final ou responde ao que foi pedido. "
            "Ações destrutivas como limpar o histórico ou remover favoritos requerem confirmação. "
            "Se detetares uma página de login, avisa o utilizador."
        )

        tools = [
            {
                "name": "navegar",
                "description": "Navega para um URL ou pesquisa rápida.",
                "input_schema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"]
                }
            },
            {
                "name": "clicar",
                "description": "Clica num elemento (botão, link, etc) especificado pelo texto ou seletor.",
                "input_schema": {
                    "type": "object",
                    "properties": {"texto": {"type": "string"}},
                    "required": ["texto"]
                }
            },
            {
                "name": "ler_pagina",
                "description": "Extrai e lê o conteúdo principal da página (ignora menus).",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "onde_estou",
                "description": "Diz o título e URL da página atual.",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "ajustar_voz",
                "description": "Ajusta volume ou velocidade da fala.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "enum": ["volume", "velocidade"]},
                        "delta": {"type": "number", "description": "Valor a somar/subtrair"}
                    },
                    "required": ["tipo", "delta"]
                }
            },
            {
                "name": "limpar_historico",
                "description": "Apaga o histórico de navegação (AÇÃO DESTRUTIVA).",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "escrever",
                "description": "Escreve um determinado texto no campo de texto focado do browser.",
                "input_schema": {
                    "type": "object",
                    "properties": {"texto": {"type": "string"}},
                    "required": ["texto"]
                }
            },
            {
                "name": "pressionar_enter",
                "description": "Pressiona a tecla Enter no browser para enviar formulários ou pesquisas.",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "pesquisar_google",
                "description": "Efetua uma pesquisa rápida no Google por um determinado termo ou frase.",
                "input_schema": {
                    "type": "object",
                    "properties": {"termo": {"type": "string"}},
                    "required": ["termo"]
                }
            },
            {
                "name": "ler_ecra_ocr",
                "description": "Lê o conteúdo visível do ecrã usando OCR (útil para páginas com conteúdo dinâmico ou imagens).",
                "input_schema": {"type": "object", "properties": {}}
            }
        ]

        # Início do Loop de 5 iterações
        for i in range(5):
            # Iniciar o Talker antes do pedido ao Claude
            if self._talker:
                self._talker.iniciar_comando("default")

            try:
                modelo = self.config.get("claude", {}).get("modelo", "claude-3-5-sonnet-20240620")
                max_tok = self.config.get("claude", {}).get("max_tokens", 1024)
                res = self.client.messages.create(
                    model=modelo,
                    max_tokens=max_tok,
                    system=system_prompt,
                    messages=hist,
                    tools=tools
                )
            finally:
                # Parar o Talker assim que a API responder
                if self._talker:
                    self._talker.parar()

            texto = ""
            tool_calls = [block for block in res.content if block.type == "tool_use"]

            if tool_calls:
                hist.append({"role": "assistant", "content": res.content})
                
                tool_results = []
                for block in tool_calls:
                    # Verificar se é ação destrutiva (Func 3)
                    if block.name == "limpar_historico":
                        self._pendente_confirmacao = (block.name, {}, "Tens a certeza que queres apagar todo o teu histórico?")
                        msg = "Essa é uma ação permanente. Tens a certeza que queres apagar o histórico?"
                        self._falar(msg)
                        return msg

                    # Iniciar o Talker antes da execução da ferramenta
                    if self._talker:
                        self._talker.iniciar_comando(block.name)

                    console.print(f"[yellow]🛠 Tool: {block.name}({block.input})[/yellow]")
                    resultado = self._exec(block.name, block.input)

                    # Parar o Talker após execução da ferramenta
                    if self._talker:
                        self._talker.parar()
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(resultado)
                    })

                hist.append({
                    "role": "user",
                    "content": tool_results
                })
                continue # Re-invoca Claude com os resultados obtidos
            else:
                # Se não houver chamadas de ferramentas, a resposta é final
                texto = "".join([block.text for block in res.content if block.type == "text"])
                if texto:
                    self._falar(texto)
                return texto

        return "Não consegui terminar, tenta um pedido mais simples."

    # ------------------------------------------------------------------
    # INTERNO / TOOLS
    # ------------------------------------------------------------------

    def _exec(self, nome: str, params: dict) -> dict:
        if nome not in self._cb: return {"erro": "ferramenta indisponível"}
        if params is None:
            params = {}
        try:
            return self._cb[nome](**params)
        except Exception as e:
            return {"erro": str(e)}

    def _exec_shortcut(self, acao: str) -> dict:
        """Executa uma ação de atalho (ex: 'navegar para youtube.com')."""
        if acao.startswith("navegar para "):
            url = acao.replace("navegar para ", "")
            return self._exec("navegar", {"url": url})
        return {"erro": "atalho não reconhecido"}

    def _falar(self, texto: str):
        if self._falar_cb:
            self._falar_cb(texto, nao_bloquear=True)