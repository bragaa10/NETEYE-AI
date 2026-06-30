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
        self._cache = {} # {comando_limpo: (resposta_texto, acao_nome, params, timestamp)}
        self._cache_expiry = 1800 # 30 min
        self._last_url = ""
        
        # Estado de Confirmação (Func 3) — usado APENAS para ações destrutivas reais
        self._pendente_confirmacao = None # (acao, params, msg_pergunta)

        # Estado de pergunta pendente — qualquer pergunta sim/não/escolha feita pela IA
        # (ex: "queres que eu clique na playlist?") fica registada aqui, para que a
        # próxima resposta do utilizador ("sim") seja sempre enviada ao Claude como
        # resposta a ESSA pergunta, em vez de cair no cache ou ser tratada como comando novo.
        self._pergunta_pendente = False
        self._ultimo_hist = None  # guarda o histórico da conversa anterior para dar continuidade

        # Lista de palavras curtas que NUNCA devem ser respondidas via cache, porque
        # o seu significado depende inteiramente do contexto da pergunta anterior.
        self._RESPOSTAS_CONTEXTUAIS = {
            "sim", "não", "nao", "ok", "pode ser", "confirmo", "vai", "força",
            "claro", "exato", "isso", "afirmativo", "negativo", "cancela", "para",
        }

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
        if self.talker_ativo and not self._talker:
            try:
                from core.talker import Talker
                self._talker = Talker(func, self.api_key)
            except Exception as e:
                console.print(f"[red]Erro ao inicializar Talker: {e}[/red]")

    def registar_screenshot(self, func):
        self._get_screenshot = func

    def atualizar_atalhos(self, lista_atalhos: list):
        """Atualiza o dicionário de atalhos locais."""
        self._atalhos = {a["frase"].lower().strip(): a["acao"] for a in lista_atalhos if isinstance(a, dict) and "frase" in a and "acao" in a}

    # ------------------------------------------------------------------
    # PROCESSAMENTO PRINCIPAL
    # ------------------------------------------------------------------

    def processar(self, comando: str, user_id: int = 1):
        """Processa um comando de voz com lógica sénior."""
        if not self.client:
            self._falar("Desculpa, preciso de uma chave de API válida para funcionar. Configura a chave nas definições.")
            return
        cmd_limpo = comando.lower().strip()
        
        # 1. Verificar Estado de Confirmação DESTRUTIVA (Func 3) — ações irreversíveis
        if self._pendente_confirmacao:
            if "sim" in cmd_limpo or "pode ser" in cmd_limpo or "confirmo" in cmd_limpo:
                acao, params, _ = self._pendente_confirmacao
                self._pendente_confirmacao = None
                self._pergunta_pendente = False
                res = self._exec(acao, params)
                if "erro" in res:
                    msg = f"Ocorreu um erro ao executar a ação: {res['erro']}"
                else:
                    msg = f"Ação confirmada e executada. {res.get('ok', '')}"
                self._falar(msg)
                # Registar na DB
                if "registar_comando" in self._cb: self._cb["registar_comando"](user_id, comando, msg)
                return
            elif "não" in cmd_limpo or "cancela" in cmd_limpo:
                self._pendente_confirmacao = None
                self._pergunta_pendente = False
                self._falar("Está bem, cancelei a ação.")
                return
            else:
                self._falar("Não entendi. Diz 'sim' para confirmar ou 'não' para cancelar.")
                return

        # 2. Verificar se há uma PERGUNTA PENDENTE da IA (ex: "queres que clique nisto?")
        # Comandos curtos e ambíguos (sim, não, ok, vai...) NUNCA passam por atalhos
        # ou cache quando há uma pergunta pendente — vão sempre direto ao Claude,
        # com o histórico da conversa anterior, para que a resposta tenha contexto real.
        if self._pergunta_pendente and cmd_limpo in self._RESPOSTAS_CONTEXTUAIS:
            console.print("[dim cyan]↳ Resposta contextual a pergunta pendente — a continuar a conversa anterior.[/dim cyan]")
            hist = self._ultimo_hist or []
            hist.append({"role": "user", "content": comando})
            try:
                resposta_final, tools_called = self._loop_claude(hist, user_id)
                if "registar_comando" in self._cb:
                    self._cb["registar_comando"](user_id, comando, resposta_final)
            except Exception as e:
                console.print(f"[red]Erro Assistant: {e}[/red]")
                self._falar("Desculpa, tive um erro ao processar a tua resposta.")
            return

        # Se chegou aqui e havia uma pergunta pendente mas o comando não é uma resposta
        # contextual simples (ex: o utilizador mudou de assunto), limpamos o estado.
        self._pergunta_pendente = False

        # 3. Verificar Atalhos Personalizados (Func 6)
        if cmd_limpo in self._atalhos:
            acao = self._atalhos[cmd_limpo]
            console.print(f"[bold blue]⚡ Atalho detetado: {cmd_limpo} -> {acao}[/bold blue]")
            res = self._exec_shortcut(acao)
            msg = f"A executar atalho para {cmd_limpo}."
            self._falar(msg)
            if "registar_comando" in self._cb: self._cb["registar_comando"](user_id, comando, msg)
            return

        # 4. Verificar Cache (Func 10)
        # IMPORTANTE: nunca usar cache para respostas contextuais curtas (sim/não/ok/...),
        # mesmo fora do fluxo de pergunta pendente — estas palavras têm significado
        # diferente consoante a conversa e nunca devem ser respondidas "de cor".
        usar_cache = cmd_limpo not in self._RESPOSTAS_CONTEXTUAIS

        cache_manager = getattr(self, "_cache_manager", None)
        if usar_cache and cache_manager:
            cached = cache_manager.obter_comando_cache(cmd_limpo)
            if cached:
                console.print("[dim green]🚀 Cache hit (CacheManager)![/dim green]")
                resp = cached.get("resposta")
                acao = cached.get("acao")
                params = cached.get("params")
                if acao: self._exec(acao, params)
                if resp: self._falar(resp)
                return
        elif usar_cache and cmd_limpo in self._cache:
            resp, acao, params, timestamp = self._cache[cmd_limpo]
            if time.time() - timestamp < self._cache_expiry:
                console.print("[dim green]🚀 Cache hit (Memória Local)![/dim green]")
                if acao: self._exec(acao, params)
                self._falar(resp)
                return

        # 5. Processamento Claude (Tool Use)
        hist = [{"role":"user","content":comando}]
        try:
            # Enviar para o loop de iterações do Claude
            resposta_final, tools_called = self._loop_claude(hist, user_id)
            
            # Se for um comando simples (sem parâmetros complexos) E não executou ferramentas
            # E não é uma resposta contextual, guardar em cache
            if usar_cache and len(comando.split()) < 4 and not tools_called:
                if cache_manager:
                    cache_manager.cache_comando(cmd_limpo, {"resposta": resposta_final, "acao": None, "params": None})
                else:
                    self._cache[cmd_limpo] = (resposta_final, None, None, time.time())
                
            if "registar_comando" in self._cb: 
                self._cb["registar_comando"](user_id, comando, resposta_final)
                
        except Exception as e:
            console.print(f"[red]Erro Assistant: {e}[/red]")
            self._falar("Desculpa, tive um erro ao processar o teu pedido.")

    def _pruning_historico(self, hist: list) -> list:
        """
        Mantém o último bloco de mensagens (resultados de ferramentas mais recentes) intacto,
        mas trunca o conteúdo de tool_results de turnos anteriores e remove imagens antigas
        para economizar tokens nas iterações seguintes.
        """
        if len(hist) <= 2:
            return hist
            
        novo_hist = []
        for idx, msg in enumerate(hist[:-1]):
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                novo_content = []
                for block in msg["content"]:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_result":
                            content_str = block.get("content", "")
                            if len(content_str) > 500:
                                block_copy = block.copy()
                                block_copy["content"] = content_str[:500] + "\n[Conteúdo truncado para economizar tokens nas iterações seguintes]"
                                novo_content.append(block_copy)
                            else:
                                novo_content.append(block)
                        elif block.get("type") == "image":
                            # Não incluir imagens antigas para poupar tokens
                            continue
                        else:
                            novo_content.append(block)
                    else:
                        novo_content.append(block)
                msg_copy = msg.copy()
                msg_copy["content"] = novo_content
                novo_hist.append(msg_copy)
            else:
                novo_hist.append(msg)
                
        novo_hist.append(hist[-1])
        return novo_hist

    def _obter_imagem_block(self) -> dict | None:
        if not self._get_screenshot:
            return None
        img_bytes = self._get_screenshot()
        if not img_bytes:
            return None
        import base64
        base64_img = base64.b64encode(img_bytes).decode("utf-8")
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64_img
            }
        }

    def _loop_claude(self, hist: list, user_id: int) -> tuple:
        # Instruções de Sistema (Persona Sénior)
        system_prompt = (
            "És o NetEye, um assistente de voz para navegação web concebido para utilizadores invisuais. "
            "Fala de forma natural, calorosa e coloquial, como numa conversa normal. "
            "Responde sempre de forma extremamente concisa, com no máximo duas frases curtas. "
            "Nunca uses listas, marcadores, bullets, asteriscos ou formatação markdown, pois a tua resposta será lida por um sintetizador de voz. "
            "Não descrevas os passos técnicos que fizeste; diz diretamente o resultado final ou responde ao que foi pedido. "
            "Ações destrutivas como limpar o histórico ou remover favoritos requerem confirmação. "
            "Se detetares uma página de login, avisa o utilizador. "
            "\nREGRAS CRÍTICAS DE FIABILIDADE DO ESTADO DA PÁGINA:\n"
            "1. Nunca confirmes que uma ação (como um clique ou preenchimento de campo) foi bem-sucedida se a ferramenta correspondente falhou (recebeu erro no tool_result).\n"
            "2. Se uma ferramenta retornar um erro ou falha no resultado (indicado por is_error: true), assume e diz explicitamente que a ação falhou (ex: 'Não consegui clicar no resultado, queres que tente de outra forma?') e sugere uma alternativa útil.\n"
            "3. Nunca inventes ou suponhas informações que não possas confirmar diretamente através dos resultados das ferramentas de diagnóstico (OCR, leitura de página, onde estou). Se uma destas ferramentas falhar ou disser que houve erro de diagnóstico, admite claramente que não conseguiste obter essa informação (ex: 'Não consegui ler o ecrã' ou 'Não consegui verificar isso').\n"
            "4. Quando o resultado de um clique vier acompanhado de um screenshot, OLHA atentamente para a imagem antes de descrever o que aconteceu. Não assumas que clicaste no elemento certo só porque a ferramenta devolveu sucesso — confirma visualmente o título do vídeo, o texto do botão ou o conteúdo real que aparece no screenshot antes de descrever o resultado ao utilizador.\n"
            "5. Se o utilizador disser que clicaste no elemento errado (ex: 'isso é um anúncio', 'não era esse'), confia totalmente nele, pede desculpa de forma breve e tenta corrigir com a próxima ação — nunca discutas ou repitas a afirmação anterior.\n"
            "6. Quando o texto que pretendes clicar for ambíguo, genérico ou quando os elementos clicáveis óbvios (botões com texto claro) não resolverem a tarefa, usa a ferramenta ler_ecra_ocr para confirmar visualmente o conteúdo do ecrã antes de tentar clicar — não dependas apenas de suposições sobre o que está na página.\n"
            "7. Em páginas de resultados do YouTube ou Google, distingue claramente anúncios patrocinados (geralmente marcados como 'Patrocinado', 'Ad' ou no topo da lista) dos resultados orgânicos — prefere sempre clicar no primeiro resultado orgânico, a menos que o utilizador peça explicitamente um anúncio."
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
                "description": "Clica num elemento visível na página (botão, link, etc) especificado pelo texto. NÃO uses para pesquisar no YouTube ou Google — usa pesquisar_youtube ou pesquisar_google em vez disso.",
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
                "description": "Escreve texto num campo de pesquisa ou formulário visível na página. Para pesquisar no YouTube, usa pesquisar_youtube em vez disto.",
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
                "name": "pesquisar_youtube",
                "description": "Pesquisa um vídeo ou música diretamente no YouTube. Navega para o YouTube automaticamente, escreve o termo na barra de pesquisa e submete. Usa sempre esta ferramenta quando o utilizador pedir para procurar algo no YouTube.",
                "input_schema": {
                    "type": "object",
                    "properties": {"termo": {"type": "string", "description": "O termo a pesquisar no YouTube"}},
                    "required": ["termo"]
                }
            },
            {
                "name": "ler_ecra_ocr",
                "description": "Lê o conteúdo visível do ecrã usando OCR (útil para páginas com conteúdo dinâmico ou imagens).",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "obter_estrutura_cabecalhos",
                "description": "Obtém a estrutura de cabeçalhos (H1 a H6) da página atual, permitindo navegação estrutural.",
                "input_schema": {"type": "object", "properties": {}}
            }
        ]

        # Guardar ferramentas chamadas neste loop para detetar runaway loops e flag de ferramentas ativas
        historico_ferramentas = []
        tools_called = False

        # Obter screenshot inicial e estruturar a primeira mensagem do utilizador como lista
        if hist and len(hist) == 1 and hist[0]["role"] == "user" and isinstance(hist[0]["content"], str):
            comando_texto = hist[0]["content"]
            content_list = [{"type": "text", "text": comando_texto}]
            img_block = self._obter_imagem_block()
            if img_block:
                content_list.append(img_block)
            hist[0]["content"] = content_list

        # Início do Loop de 5 iterações
        for i in range(5):
            # Iniciar o Talker antes do pedido ao Claude
            if self._talker:
                self._talker.iniciar_comando("default")

            try:
                # Usar sempre o modelo configurado como principal. Todos os modelos
                # Claude atuais (incluindo o Haiku) já têm suporte nativo a visão —
                # trocar para um modelo mais lento (Sonnet) só por haver uma imagem
                # no histórico adiciona latência sem necessidade real. O modelo
                # de visão dedicado fica reservado apenas como fallback em caso
                # de erro de modelo (ver bloco de fallback abaixo).
                modelo = self.config.get("claude", {}).get("modelo", "claude-haiku-4-5-20251001")
                
                max_tok = self.config.get("claude", {}).get("max_tokens", 1024)
                
                # Cópia das ferramentas com Prompt Caching (Beta)
                cached_tools = []
                for idx, tool in enumerate(tools):
                    tool_copy = tool.copy()
                    if idx == len(tools) - 1:
                        tool_copy["cache_control"] = {"type": "ephemeral"}
                    cached_tools.append(tool_copy)

                # Pruning de mensagens anteriores em hist
                hist_enviado = self._pruning_historico(hist)

                # Active prompt caching on system prompt block
                system_blocks = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]

                try:
                    res = self.client.messages.create(
                        model=modelo,
                        max_tokens=max_tok,
                        system=system_blocks,
                        messages=hist_enviado,
                        tools=cached_tools,
                        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
                    )
                except Exception as e:
                    err_str = str(e).lower()
                    is_not_found = "404" in err_str or "not_found" in err_str or "model" in err_str
                    fallback_model = "claude-sonnet-4-6"
                    if is_not_found and modelo != fallback_model:
                        console.print(f"[yellow]⚠️ Modelo {modelo} indisponível. A tentar fallback para {fallback_model}...[/yellow]")
                        modelo = fallback_model
                        res = self.client.messages.create(
                            model=modelo,
                            max_tokens=max_tok,
                            system=system_blocks,
                            messages=hist_enviado,
                            tools=cached_tools,
                            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
                        )
                    else:
                        raise
            finally:
                # Parar o Talker assim que a API responder
                if self._talker:
                    self._talker.parar()

            texto = ""
            tool_calls = [block for block in res.content if block.type == "tool_use"]

            if tool_calls:
                hist.append({"role": "assistant", "content": res.content})
                tools_called = True
                
                tool_results = []
                for block in tool_calls:
                    # Runaway Loop Guard
                    arg_str = json.dumps(block.input, sort_keys=True)
                    call_key = (block.name, arg_str)
                    historico_ferramentas.append(call_key)
                    
                    if historico_ferramentas.count(call_key) > 2:
                        console.print(f"[bold red]⚠️ Runaway loop guard ativado: {block.name}({arg_str})[/bold red]")
                        msg_aviso = "Desculpa, percebi que estamos a tentar a mesma ação repetidamente sem sucesso. Podes tentar reformular o pedido?"
                        self._falar(msg_aviso)
                        return msg_aviso, True

                    # Verificar se é ação destrutiva (Func 3)
                    if block.name == "limpar_historico":
                        self._pendente_confirmacao = (block.name, {}, "Tens a certeza que queres apagar todo o teu histórico?")
                        msg = "Essa é uma ação permanente. Tens a certeza que queres apagar o histórico?"
                        self._falar(msg)
                        return msg, True

                    # Iniciar o Talker antes da execução da ferramenta
                    if self._talker:
                        self._talker.iniciar_comando(block.name)

                    console.print(f"[yellow]🛠 Tool: {block.name}({block.input})[/yellow]")
                    resultado = self._exec(block.name, block.input)

                    # Parar o Talker após execução da ferramenta
                    if self._talker:
                        self._talker.parar()
                    
                    # Detetar se o resultado representa erro/falha
                    is_error = False
                    if resultado is None:
                        is_error = True
                    elif isinstance(resultado, dict):
                        if resultado.get("sucesso") is False or "erro" in resultado:
                            is_error = True
                            
                    res_block = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(resultado)
                    }
                    if is_error:
                        res_block["is_error"] = True

                    tool_results.append(res_block)

                # Obter screenshot atualizada após a execução das ferramentas para a próxima iteração
                img_block = self._obter_imagem_block()
                if img_block:
                    tool_results.append(img_block)

                hist.append({
                    "role": "user",
                    "content": tool_results
                })
                continue # Re-invoca Claude com os resultados obtidos
            else:
                # Se não houver chamadas de ferramentas, a resposta é final
                texto = "".join([getattr(block, 'text', '') for block in res.content if block.type == "text"])
                if texto:
                    self._falar(texto)

                # Detetar se a IA terminou a resposta com uma pergunta — nesse caso,
                # guardamos o histórico completo e marcamos pergunta_pendente=True,
                # para que um "sim"/"não" subsequente seja tratado como resposta
                # a ESTA pergunta, com contexto, em vez de cair no cache ou ser
                # processado como comando novo desligado da conversa.
                texto_strip = texto.strip()
                parece_pergunta = texto_strip.endswith("?") or texto_strip.endswith("?\"")
                if parece_pergunta:
                    hist.append({"role": "assistant", "content": texto})
                    self._ultimo_hist = hist
                    self._pergunta_pendente = True
                else:
                    self._pergunta_pendente = False
                    self._ultimo_hist = None

                return texto, tools_called

        return "Não consegui terminar, tenta um pedido mais simples.", tools_called

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