"""
NetEye — main.py (INTEGRAÇÃO SÉNIOR)
====================================
Orquestrador principal com suporte a todas as 14 funcionalidades seniores.
[OTIMIZAÇÃO] Integrado com cache, connection pool, logging e I/O paralelo.
"""
import os
import argparse
import threading
import yaml
import time
import sys
import atexit
import json
# Configurar codificação UTF-8 para consola para evitar erros com emojis no Windows (cp1252)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.panel   import Panel
from rich.text    import Text

console = Console()
load_dotenv()

from core.browser    import BrowserController, obter_browser, fechar_browser_global
from core.assistant  import Assistant
from core.eleven_speaker import ElevenSpeaker
from core.database   import Database
from core.audio_engine import audio_engine

# Importar módulos de otimização (não afetam funcionamento)
try:
    from core.cache_manager import CacheManager
    from core.log_manager import obter_logger
    from core.async_io import obter_async_manager
    _otimizacoes_disponiveis = True
except ImportError as e:
    _otimizacoes_disponiveis = False
    console.print(f"[yellow]⚠️ Módulos de otimização não disponíveis: {e}[/yellow]")


# FIX: Conversores seguros para dados não confiáveis vindo da base de dados.
def safe_int(value, default=0):
    """Converte valor para int com fallback seguro."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_float(value, default=0.0):
    """Converte valor para float com fallback seguro."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

class NetEye:
    def __init__(self, config, user_id, api_key=None, usar_browser=True, modo_texto=False):
        self.config     = config
        self.user_id    = user_id
        self.modo_texto = modo_texto
        self._stop_event = threading.Event()
        # Sinalizado quando o EasyOCR termina o pré-carregamento em background.
        # Se o módulo Vision não estiver disponível, é marcado de imediato (não bloqueia).
        self._ocr_pronto = threading.Event()
        # Rastreia o último URL conhecido para detetar navegação real causada por cliques
        self._ultima_url_conhecida = ""
        
        # Stats da Sessão (Func 11)
        self.stats = {
            "inicio": time.time(),
            "comandos": 0,
            "visitas": 0,
            "erros": 0
        }
        
        # Inicializar cache e logging (otimizações)
        if _otimizacoes_disponiveis:
            self.cache = CacheManager()
            self.logger = obter_logger()
            self.async_io = obter_async_manager()
        else:
            self.cache = None
            self.logger = None
            self.async_io = None

        # 1. DB e Atalhos (Func 6)
        self.db = Database()
        atalhos = self.db.listar_atalhos(user_id)

        # 2. Configurações por Utilizador (Func 5)
        db_configs = self.db.obter_todas_configuracoes(user_id)
        local_backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "local_config_backup.json")
        
        if db_configs:
            try:
                os.makedirs(os.path.dirname(local_backup_path), exist_ok=True)
                backup_data = db_configs.copy()
                if "api_key" in backup_data and backup_data["api_key"]:
                    backup_data["api_key"] = self.db._encrypt(backup_data["api_key"])
                with open(local_backup_path, "w", encoding="utf-8") as f:
                    json.dump(backup_data, f, indent=2)
            except Exception:
                pass
        else:
            try:
                if os.path.exists(local_backup_path):
                    console.print("[yellow]⚠️ Supabase indisponível. A carregar configurações do backup local...[/yellow]")
                    with open(local_backup_path, "r", encoding="utf-8") as f:
                        db_configs = json.load(f)
            except Exception:
                pass

        for k, v in db_configs.items():
            # FIX: Usar conversores seguros para dados da DB (não confiáveis).
            if k == "velocidade": config["assistente"]["rate"] = safe_int(v)
            if k == "volume": config["assistente"]["volume"] = safe_float(v) / 100.0
            if k == "idioma": config["assistente"]["idioma"] = v
            if k == "modo_headless": config["browser"]["modo_headless"] = (v == "True")
            if k == "talker_ativo": config["assistente"]["talker_ativo"] = (v == "True")
            if k == "voz_local": config["assistente"]["voz_local"] = v
            if k == "interromper_ao_falar": config["vad"]["interromper_ao_falar"] = (v == "True")
            if k == "guardar_historico": config["assistente"]["guardar_historico"] = (v == "True")

        # Fetch and decrypt API key from database if not provided via environment or CLI
        if not api_key:
            db_api_key = db_configs.get("api_key")
            if db_api_key:
                try:
                    # If it's already plain (like if it was not encrypted in backup), use it, otherwise decrypt
                    if db_api_key.startswith("gAAAAA"):
                        api_key = self.db._decrypt(db_api_key)
                    else:
                        api_key = db_api_key
                except Exception:
                    api_key = db_api_key

        # 3. Inicializar Componentes
        self.speaker = ElevenSpeaker(config["assistente"])
        self.assistant = Assistant(config, api_key)
        self.assistant.atualizar_atalhos(atalhos) # Carregar atalhos Func 6
        
        # Passar cache ao assistant (otimização)
        if self.cache:
            self.assistant._cache_manager = self.cache

        if not modo_texto:
            from core.listener    import Listener
            from core.transcriber import Transcriber
            self.listener    = Listener(config["vad"])
            self.transcriber = Transcriber(config["stt"])
        else:
            self.listener = self.transcriber = None

        # Usar browser singleton se disponível (otimização)
        if usar_browser:
            try:
                self.browser = obter_browser(config["browser"])
            except Exception:
                # Fallback para versão clássica se singleton falhar
                self.browser = BrowserController(config["browser"])
        else:
            self.browser = None
            
        self._ligar_ferramentas()
        
        console.print(f"[bold green][OK] Ready (User ID: {user_id})[/bold green]\n")

    def _ligar_ferramentas(self):
        a  = self.assistant
        br = self.browser
        db = self.db

        # Callback para registo de comandos na DB (Func 2)
        a.registar_ferramenta("registar_comando", 
            lambda user_id, cmd, resp: db.registar_comando(user_id, cmd, resp))

        if br:
            def navegar(url):
                # Verificar se o site está na lista de bloqueios (Func 13)
                bloqueios = db.listar_bloqueios(self.user_id)
                url_lower = url.lower()
                for b in bloqueios:
                    domain = b.get("url", "").lower().strip()
                    if domain and (domain in url_lower):
                        console.print(f"[bold red]🚫 Site bloqueado: {url}[/bold red]")
                        self.speaker.falar("Desculpa, esse site está na tua lista de sites bloqueados.")
                        return {"sucesso": False, "erro": "site_bloqueado", "mensagem": "Este site está bloqueado pelas tuas definições."}

                # Dar feedback imediato para sites pesados antes de iniciar o carregamento que bloqueia a thread
                if "youtube.com" in url_lower or "youtube" in url_lower:
                    self.speaker.falar("A abrir o YouTube, por favor aguarda um momento...")
                elif "instagram.com" in url_lower:
                    self.speaker.falar("A abrir o Instagram, por favor aguarda...")
                elif "facebook.com" in url_lower:
                    self.speaker.falar("A abrir o Facebook, por favor aguarda...")
                elif "amazon" in url_lower:
                    self.speaker.falar("A abrir a Amazon, por favor aguarda...")

                audio_engine.start_loop("page_loading")
                try:
                    r = br.navegar(url)
                finally:
                    audio_engine.stop_loop("page_loading")
                _tocar_resultado(r)
                if r.get("sucesso"):
                    self.stats["visitas"] += 1
                    # Verificar se guardar_historico está ativo (Padrão: True)
                    if self.config.get("assistente", {}).get("guardar_historico", True):
                        threading.Thread(target=db.registar_visita, 
                                         args=(self.user_id, r["url"], r["titulo"]), daemon=True).start()
                    # Func 12: Aviso de Login
                    if r.get("tem_login"):
                        self.speaker.falar("Detetei um formulário de login nesta página. Queres que eu preencha?")
                return r

            def clicar(texto):
                # FIX: clicar() podia levar o utilizador a uma página totalmente nova
                # (ex: clicar num vídeo do YouTube) sem que isso fosse contabilizado
                # nas estatísticas de sessão nem registado no histórico de navegação.
                # Comparamos o URL antes/depois do clique para detetar essa mudança.
                url_antes = ""
                try:
                    url_antes = br.obter_relatorio_localizacao()
                except Exception:
                    pass

                r = br.clicar_elemento(texto)
                _tocar_resultado(r)

                if r.get("sucesso"):
                    try:
                        url_atual = br._page.url if br._page else ""
                        titulo_atual = br._obter_titulo_rapido() if hasattr(br, "_obter_titulo_rapido") else ""
                    except Exception:
                        url_atual, titulo_atual = "", ""

                    # Se o clique resultou em navegação para uma página diferente,
                    # tratamos como uma visita real — conta nas estatísticas e no histórico.
                    if url_atual and url_atual != self._ultima_url_conhecida:
                        self.stats["visitas"] += 1
                        self._ultima_url_conhecida = url_atual
                        if self.config.get("assistente", {}).get("guardar_historico", True) and url_atual:
                            threading.Thread(target=db.registar_visita,
                                             args=(self.user_id, url_atual, titulo_atual), daemon=True).start()
                return r

            a.registar_ferramenta("navegar",          navegar)
            a.registar_ferramenta("pesquisar_google",  lambda termo: _com_som(br.pesquisar_google, termo))
            a.registar_ferramenta("pesquisar_youtube", lambda termo: _com_som(br.pesquisar_youtube, termo))
            a.registar_ferramenta("clicar",            clicar)
            a.registar_ferramenta("escrever",          lambda texto: _com_som(br.escrever_campo, "", texto))
            a.registar_ferramenta("escrever_em_campo", lambda campo, texto: _com_som(br.escrever_em_campo, campo, texto))
            a.registar_ferramenta("pressionar_enter",  lambda: _com_som(br.pressionar_enter))
            a.registar_ferramenta("voltar_pagina",     lambda: _com_som(br.voltar_pagina))
            a.registar_ferramenta("avancar_pagina",    lambda: _com_som(br.avancar_pagina))
            a.registar_ferramenta("recarregar_pagina", lambda: _com_som(br.recarregar_pagina))
            
            # Novas Ferramentas Sénior (Func 4 & 8)
            a.registar_ferramenta("ler_pagina",       lambda: {"conteudo": br.extrair_conteudo_principal()})
            a.registar_ferramenta("onde_estou",       lambda: {"ok": br.obter_relatorio_localizacao()})
            a.registar_ferramenta("obter_estrutura_cabecalhos", br.obter_estrutura_cabecalhos)
            a.registar_ferramenta("ir_para_cabecalho", br.ir_para_cabecalho)
            a.registar_ferramenta("obter_elementos_interativos", br.obter_elementos_interativos)
            a.registar_ferramenta("obter_memoria_navegacao", br.obter_memoria_navegacao)
            
            # Ferramenta OCR - lê o ecrã via screenshot + OCR (Func 4)
            try:
                from core.vision import Vision
                _vision = Vision()

                def _ler_ecra_ocr():
                    # FIX CRÍTICO: usar o screenshot REAL da página do browser
                    # (br.tirar_screenshot) em vez de capturar o monitor físico
                    # inteiro. Antes, o OCR podia ler qualquer coisa que estivesse
                    # visível no ecrã do computador, completamente desligado do
                    # que a página web realmente mostrava — incluindo a app de
                    # terminal, o ambiente de trabalho, etc.
                    img_bytes = br.tirar_screenshot()
                    if not img_bytes:
                        return {"texto": "[FALHA NO DIAGNÓSTICO: não foi possível capturar a página atual para leitura ótica]"}
                    texto = _vision.extrair_texto_de_bytes(img_bytes)
                    return {"texto": texto}

                a.registar_ferramenta("ler_ecra_ocr", _ler_ecra_ocr)

                # FIX: o EasyOCR demorava 20-40s a carregar na PRIMEIRA chamada,
                # bloqueando o assistente a meio de uma conversa real (visível no
                # log: "Downloading detection model..." enquanto o utilizador
                # esperava resposta). Pré-carregamos o modelo em background logo
                # no arranque, para que esteja pronto antes de ser necessário.
                # O evento self._ocr_pronto é sinalizado no fim, e iniciar() espera
                # por ele antes de aceitar o primeiro comando do utilizador.
                def _prewarm_ocr():
                    try:
                        from core.vision import _obter_reader
                        _obter_reader()
                        console.print("[dim green][OK] EasyOCR pré-carregado em background.[/dim green]")
                    except Exception as e:
                        console.print(f"[dim yellow]⚠️ Pré-carregamento OCR falhou (será carregado na primeira utilização): {e}[/dim yellow]")
                    finally:
                        self._ocr_pronto.set()
                threading.Thread(target=_prewarm_ocr, daemon=True).start()

            except ImportError:
                console.print("[dim yellow]⚠️ Módulo Vision (OCR) não disponível[/dim yellow]")
                # Sem módulo Vision não há nada a esperar — não bloquear o arranque.
                self._ocr_pronto.set()
            
            a.registar_screenshot(br.tirar_screenshot)
        else:
            # Sem browser não há OCR de página possível — não bloquear o arranque.
            self._ocr_pronto.set()

        # Controlo de Voz (Func 9)
        def ajustar_voz(tipo, delta):
            if tipo == "volume": 
                self.speaker.ajustar_volume(delta / 100.0)
                db.guardar_configuracao(self.user_id, "volume", str(int(self.speaker.volume * 100)))
            else: 
                self.speaker.ajustar_velocidade(int(delta))
                db.guardar_configuracao(self.user_id, "velocidade", str(self.speaker.rate))
            return {"ok": f"{tipo} ajustado."}

        a.registar_ferramenta("ajustar_voz", ajustar_voz)
        a.registar_ferramenta("limpar_historico", lambda: db.limpar_historico(self.user_id))
        
        a.registar_falar(self.speaker.falar)

    def iniciar(self):
        self._stop_event.clear()
        if self.browser:
            try:
                self.browser.iniciar()
            except Exception as e:
                console.print(f"[bold red]Erro fatal ao iniciar o browser: {e}[/bold red]")
                self.speaker.falar("Aviso importante: não consegui iniciar o navegador de internet. Por favor, verifica as dependências do Playwright.")
                self.browser = None
        if self.listener: self.listener.iniciar()

        # Bloquear até o EasyOCR terminar o pré-carregamento (ver _prewarm_ocr em
        # _ligar_ferramentas). Sem isto, o utilizador podia dar comandos que dependem
        # de OCR antes do modelo estar pronto, ou o assistant.py podia tentar usar a
        # ferramenta a meio do carregamento e travar a resposta de forma confusa.
        if not self._ocr_pronto.is_set():
            console.print("[dim]⏳ A aguardar conclusão do pré-carregamento do EasyOCR...[/dim]")
            self.speaker.falar("Um momento, estou a preparar o módulo de leitura visual.")
            self._ocr_pronto.wait()

        audio_engine.play("system_ready") # Feedback Func 7
        self.speaker.falar("NetEye pronto. Estou à escuta.")
        
        if self.modo_texto: self._loop_texto()
        else:               self._loop_voz()

    def parar(self):
        if self._stop_event.is_set(): return
        self._stop_event.set()
        
        # Gerar Relatório de Sessão (Func 11)
        duracao = int(time.time() - self.stats["inicio"])
        relatorio = {
            "duracao_segundos": duracao,
            "total_comandos": self.stats["comandos"],
            "total_visitas": self.stats["visitas"],
            "erros": self.stats["erros"]
        }
        self.db.guardar_relatorio_sessao(self.user_id, relatorio)
        console.print(f"[bold yellow]Relatório de sessão guardado ({duracao}s).[/bold yellow]")

        # Falar estatísticas ao encerrar (bloqueante para não interromper a fala)
        minutos = duracao // 60
        segundos = duracao % 60
        tempo_str = f"{minutos} minutos e {segundos} segundos" if minutos > 0 else f"{segundos} segundos"
        msg_stats = f"Sessão terminada. Usaste o NetEye por {tempo_str}. Executaste {self.stats['comandos']} comandos e visitaste {self.stats['visitas']} páginas."
        try:
            self.speaker.falar(msg_stats, nao_bloquear=False)
        except Exception:
            pass

        if self.listener: self.listener.parar()
        self.speaker.parar()
        if self.browser: self.browser.fechar()
        
        # Limpeza de recursos de otimização
        try:
            fechar_browser_global()  # Fechar singleton browser
        except Exception:
            pass
        
        if self.cache:
            self.cache.limpar_cache()
            console.print("[dim]🧹 Cache limpo[/dim]")
        
        if self.logger:
            stats = self.logger.obter_stats()
            console.print(f"[dim]📊 Logs: {stats['ficheiros']} ficheiro(s), {stats['tamanho_mb']}MB[/dim]")

    def _loop_voz(self):
        while not self._stop_event.is_set():
            try:
                # Se houver confirmação ou pergunta pendente, entramos no modo de confirmação rápida sem wake word.
                if self.assistant._pendente_confirmacao or self.assistant._pergunta_pendente:
                    self.speaker.esperar()
                    console.print("[yellow]⏳ A aguardar resposta rápida sem wake word...[/yellow]")
                    audio_path = self.listener.ouvir_comando(speaker=self.speaker, ignorar_wake_word=True, timeout=8.0)
                    
                    if audio_path == "TIMEOUT" or not audio_path:
                        console.print("[red]⏱️ Timeout ou sem resposta na confirmação rápida.[/red]")
                        self.assistant._pendente_confirmacao = None
                        self.assistant._pergunta_pendente = False
                        self.speaker.falar("Tempo limite esgotado. Voltei ao modo normal de escuta.")
                        continue
                    
                    self.stats["comandos"] += 1
                    cmd = self.transcriber.transcrever(audio_path, fast=True)
                    if not cmd or len(cmd.strip()) < 2:
                        # Se não entendeu, o assistant tratará como não entendido e repetirá a pergunta na próxima volta
                        self.assistant.processar("", user_id=self.user_id)
                    else:
                        self.assistant.processar(cmd, user_id=self.user_id)
                    continue

                path = self.listener.ouvir_comando(speaker=self.speaker)
                
                if path == "TIMEOUT_IDLE":
                    self.speaker.falar("Ainda estás aí? Se precisares de mim, diz 'Ei NetEye'.")
                    continue
                    
                if not path: continue

                self.stats["comandos"] += 1
                cmd = self.transcriber.transcrever(path)
                
                # Tratar caso em que o modelo Whisper ainda está a carregar
                if cmd == "MODELO_CARREGANDO":
                    self.speaker.falar("Ainda estou a carregar os meus ficheiros de voz. Por favor, aguarda dez segundos e tenta novamente.")
                    continue
                    
                if not cmd or len(cmd.strip()) < 2: continue
                
                self.assistant.processar(cmd, user_id=self.user_id)
            except KeyboardInterrupt: break
            except Exception as e:
                self.stats["erros"] += 1
                console.print(f"[red]Erro loop: {e}[/red]")
        self.parar()

    def _loop_texto(self):
        from rich.prompt import Prompt
        while not self._stop_event.is_set():
            try:
                cmd = Prompt.ask("[bold cyan]>[/bold cyan]").strip()
                if cmd.lower() in ("sair","exit"): break
                self.stats["comandos"] += 1
                self.assistant.processar(cmd, user_id=self.user_id)
            except KeyboardInterrupt: break
        self.parar()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chave-api", type=str)
    p.add_argument("--user-id",   type=int, default=1)
    p.add_argument("--texto",     action="store_true")
    p.add_argument("--headless",  action="store_true")
    args = p.parse_args()

    config_path = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    if args.headless: config["browser"]["modo_headless"] = True
    
    neteye = NetEye(config, args.user_id, api_key=args.chave_api, modo_texto=args.texto)
    try:
        neteye.iniciar()
    except KeyboardInterrupt:
        neteye.parar()
        # FIX: os._exit bypassa atexit handlers e flush de buffers. sys.exit é correto.
        sys.exit(0)

if __name__ == "__main__":
    main()