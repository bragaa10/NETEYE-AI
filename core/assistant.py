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
        # Se a página mudou, o cache de ações de navegação pode ser inválido
        if cmd_limpo in self._cache:
            resp, acao, params, timestamp = self._cache[cmd_limpo]
            if time.time() - timestamp < self._cache_expiry:
                console.print("[dim green]🚀 Cache hit![/dim green]")
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
                self._cache[cmd_limpo] = (resposta_final, None, None, time.time())
                
            if "registar_comando" in self._cb: 
                self._cb["registar_comando"](user_id, comando, resposta_final)
                
        except Exception as e:
            console.print(f"[red]Erro Assistant: {e}[/red]")
            self._falar("Desculpa, tive um erro ao processar o teu pedido.")

    def _loop_claude(self, hist: list, user_id: int) -> str:
        # Instruções de Sistema (Persona Sénior)
        system_prompt = (
            "És o NetEye, um assistente especializado em navegação web para pessoas cegas ou com baixa visão. "
            "Sê conciso, direto e usa feedback sonoro quando necessário. "
            "Ações destrutivas (apagar histórico, remover favoritos) requerem confirmação. "
            "Se detetares uma página de login, avisa o utilizador."
        )

        tools = [
            {
                "name": "navegar",
                "description": "Navega para um URL ou pesquisa rápida.",
                "input_schema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}}
                }
            },
            {
                "name": "clicar",
                "description": "Clica num elemento (botão, link, etc).",
                "input_schema": {
                    "type": "object",
                    "properties": {"texto": {"type": "string"}}
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
                    }
                }
            },
            {
                "name": "limpar_historico",
                "description": "Apaga o histórico de navegação (AÇÃO DESTRUTIVA).",
                "input_schema": {"type": "object", "properties": {}}
            }
        ]

        # Início do Loop de 5 iterações
        for i in range(5):
            res = self.client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=1024,
                system=system_prompt,
                messages=hist,
                tools=tools
            )

            texto = ""
            for block in res.content:
                if block.type == "text":
                    texto += block.text
                elif block.type == "tool_use":
                    # Verificar se é ação destrutiva (Func 3)
                    if block.name == "limpar_historico":
                        self._pendente_confirmacao = (block.name, {}, "Tens a certeza que queres apagar todo o teu histórico?")
                        msg = "Essa é uma ação permanente. Tens a certeza que queres apagar o histórico?"
                        self._falar(msg)
                        return msg

                    # Execução Normal
                    console.print(f"[yellow]🛠 Tool: {block.name}({block.input})[/yellow]")
                    resultado = self._exec(block.name, block.input)
                    
                    hist.append({"role": "assistant", "content": res.content})
                    hist.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(resultado)
                            }
                        ]
                    })
                    break # Re-invocar Claude com resultado
            else:
                # Se saiu do loop sem break (sem tool_use), a resposta é final
                if texto: self._falar(texto)
                return texto

        return "Não consegui terminar, tenta um pedido mais simples."

    # ------------------------------------------------------------------
    # INTERNO / TOOLS
    # ------------------------------------------------------------------

    def _exec(self, nome: str, params: dict) -> dict:
        if nome not in self._cb: return {"erro": "ferramenta indisponível"}
        
        # Bug 7: Verificação de bloqueios (já implementada na fase anterior)
        # [Adicionada lógica de bloqueios aqui se necessário...]

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