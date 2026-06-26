"""
NetEye — main.py (INTEGRAÇÃO SÉNIOR)
====================================
Orquestrador principal com suporte a todas as 14 funcionalidades seniores.
[OTIMIZAÇÃO] Integrado com cache, connection pool, logging e I/O paralelo.
"""
import os, argparse, threading, yaml, time, sys
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
        self._a_correr  = False
        
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
        for k, v in db_configs.items():
            # FIX: Usar conversores seguros para dados da DB (não confiáveis).
            if k == "velocidade": config["assistente"]["rate"] = safe_int(v)
            if k == "volume": config["assistente"]["volume"] = safe_float(v) / 100.0
            if k == "idioma": config["assistente"]["idioma"] = v
            if k == "modo_headless": config["browser"]["modo_headless"] = (v == "True")
            if k == "talker_ativo": config["assistente"]["talker_ativo"] = (v == "True")
            if k == "voz_local": config["assistente"]["voice_id"] = v
            if k == "interromper_ao_falar": config["vad"]["interromper_ao_falar"] = (v == "True")
            if k == "guardar_historico": config["assistente"]["guardar_historico"] = (v == "True")

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

                self.stats["visitas"] += 1
                r = br.navegar(url)
                if r.get("sucesso"):
                    # Verificar se guardar_historico está ativo (Padrão: True)
                    if self.config.get("assistente", {}).get("guardar_historico", True):
                        threading.Thread(target=db.registar_visita, 
                                         args=(self.user_id, r["url"], r["titulo"]), daemon=True).start()
                    # Func 12: Aviso de Login
                    if r.get("tem_login"):
                        self.speaker.falar("Detetei um formulário de login nesta página. Queres que eu preencha?")
                return r

            a.registar_ferramenta("navegar",          navegar)
            a.registar_ferramenta("pesquisar_google",  br.pesquisar_google)
            a.registar_ferramenta("clicar",            br.clicar_elemento)
            a.registar_ferramenta("escrever",          lambda texto: br.escrever_campo("", texto))
            a.registar_ferramenta("pressionar_enter",  br.pressionar_enter)
            
            # Novas Ferramentas Sénior (Func 4 & 8)
            a.registar_ferramenta("ler_pagina",       lambda: {"conteudo": br.extrair_conteudo_principal()})
            a.registar_ferramenta("onde_estou",       lambda: {"ok": br.obter_relatorio_localizacao()})
            
            # Ferramenta OCR - lê o ecrã via screenshot + OCR (Func 4)
            try:
                from core.vision import Vision
                _vision = Vision()
                a.registar_ferramenta("ler_ecra_ocr", lambda: {"texto": _vision.extrair_texto_screenshot()})
            except ImportError:
                console.print("[dim yellow]⚠️ Módulo Vision (OCR) não disponível[/dim yellow]")
            
            a.registar_screenshot(br.tirar_screenshot)

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
        self._a_correr = True
        if self.browser:
            try:
                self.browser.iniciar()
            except Exception as e:
                console.print(f"[bold red]Erro fatal ao iniciar o browser: {e}[/bold red]")
                self.speaker.falar("Aviso importante: não consegui iniciar o navegador de internet. Por favor, verifica as dependências do Playwright.")
                self.browser = None
        if self.listener: self.listener.iniciar()
        
        audio_engine.play("system_ready") # Feedback Func 7
        self.speaker.falar("NetEye pronto. Estou à escuta.")
        
        if self.modo_texto: self._loop_texto()
        else:               self._loop_voz()

    def parar(self):
        if not self._a_correr: return
        self._a_correr = False
        
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
        while self._a_correr:
            try:
                # Se houver confirmação pendente, entramos no modo de confirmação rápida!
                if self.assistant._pendente_confirmacao:
                    self.speaker.esperar()
                    console.print("[yellow]⏳ A aguardar confirmação rápida (sim/não)...[/yellow]")
                    audio_path = self.listener.ouvir_comando(speaker=self.speaker, ignorar_wake_word=True, timeout=10.0)
                    
                    if audio_path == "TIMEOUT" or not audio_path:
                        console.print("[red]⏱️ Timeout ou sem resposta na confirmação rápida.[/red]")
                        self.assistant._pendente_confirmacao = None
                        self.speaker.falar("Tempo limite esgotado. Ação cancelada.")
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
        while self._a_correr:
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
