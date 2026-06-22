"""
NetEye — core/eleven_speaker.py (FILA DE REPRODUÇÃO + MELHORIAS SÉNIOR)
========================================================================
- Implementação moderna usando ElevenLabs SDK v1.x
- Streaming real-time via sounddevice e numpy
- Fila (Queue) dedicada para evitar sobreposição de áudio
- [NOVO] Controlo de Volume e Velocidade em tempo real (Func 9)
- [NOVO] Integração com AudioEngine para SFX (Func 7)
- [NOVO] Suporte a Idioma Dinâmico (Func 5)
"""

import os
import threading
import time
import queue
import numpy as np
import sounddevice as sd
from typing import Optional
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from rich.console import Console
from core.audio_engine import audio_engine, audio_lock
import re as _re

console = Console()

class ElevenSpeaker:
    def __init__(self, config: dict):
        self.api_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID") or os.getenv("ELEVEN_VOICE_ID") or config.get("voice_id", "XrExE9yKIg1WjnnlVkGX")
        self.model_id = config.get("model_id", "eleven_turbo_v2_5")
        
        # Configurações dinâmicas (Func 9)
        self.rate = config.get("rate", 160)
        self.volume = config.get("volume", 1.0)
        self.idioma = config.get("idioma", "pt-PT")
        
        self.voice_settings = VoiceSettings(
            stability=config.get("stability", 0.5),
            similarity_boost=config.get("similarity_boost", 0.8),
            style=config.get("style", 0.0),
            use_speaker_boost=config.get("use_speaker_boost", True)
        )

        self._falando = False
        self._lock = threading.Lock()
        self._stream: Optional[sd.OutputStream] = None
        self._stop_event = threading.Event()
        
        # Fila de reprodução
        self._queue = queue.Queue()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

        if self.api_key and not self.api_key.startswith("your_"):
            try:
                self.client = ElevenLabs(api_key=self.api_key)
                console.print(f"[dim green]✓ ElevenLabs pronto (Voz: {self.voice_id})[/dim green]")
            except Exception as e:
                console.print(f"[bold red]Erro ao inicializar ElevenLabs:[/bold red] {e}")
                self.client = None
        else:
            self.client = None
            console.print("[yellow]⚠️ ElevenLabs sem API Key - Fallback local ativado[/yellow]")

    # ------------------------------------------------------------------
    # CONTROLO DINÂMICO (Func 9)
    # ------------------------------------------------------------------

    def ajustar_volume(self, delta: float):
        """Ajusta o volume (0.0 a 2.0). Delta pode ser positivo ou negativo."""
        self.volume = max(0.0, min(2.0, self.volume + delta))
        console.print(f"[dim]🔊 Volume: {int(self.volume * 100)}%[/dim]")

    def ajustar_velocidade(self, delta: int):
        """Ajusta a velocidade (rate). Delta pode ser positivo ou negativo."""
        self.rate = max(50, min(400, self.rate + delta))
        console.print(f"[dim]⏩ Velocidade: {self.rate}[/dim]")

    def mudar_idioma(self, novo_idioma: str):
        """Muda o idioma de fala."""
        self.idioma = novo_idioma
        console.print(f"[dim]🌐 Idioma fala: {self.idioma}[/dim]")

    # ------------------------------------------------------------------
    # API PÚBLICA
    # ------------------------------------------------------------------

    def falar(self, texto: str, nao_bloquear: bool = False, som_inicio: str = None):
        """
        Adiciona texto à fila para conversão em fala.
        O parâmetro som_inicio permite tocar um SFX antes de falar (Func 7).
        """
        if not texto or not texto.strip():
            return

        text_clean = texto.strip()
        console.print(f"[cyan]🔊[/cyan] {text_clean}")

        if som_inicio:
            audio_engine.play(som_inicio)

        self._queue.put(text_clean)

        if not nao_bloquear:
            self.esperar()

    def tocar_som(self, nome_som: str):
        """Toca um efeito sonoro diretamente."""
        audio_engine.play(nome_som)

    def parar(self):
        """Interrompe imediatamente qualquer fala em curso e limpa a fila."""
        self._stop_event.set()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        
        self._falando = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except:
                pass
        self._stream = None

    def esta_a_falar(self) -> bool:
        return self._falando or not self._queue.empty()

    def esperar(self):
        while self.esta_a_falar():
            time.sleep(0.05)

    # ------------------------------------------------------------------
    # INTERNO
    # ------------------------------------------------------------------

    def _worker(self):
        while True:
            try:
                texto = self._queue.get()
                if texto is None: break 
                
                self._executar(texto)
                self._queue.task_done()
            except Exception as e:
                console.print(f"[red]Erro no worker de áudio: {e}[/red]")
                time.sleep(0.1)

    def _executar(self, texto: str):
        with self._lock:
            self._stop_event.clear()
            self._falando = True
            
            try:
                if self.client:
                    self._falar_streaming(texto)
                else:
                    self._fallback_local(texto)
            except Exception as e:
                console.print(f"[red]Erro TTS (streaming): {e}[/red]")
                self._fallback_local(texto)
            finally:
                self._falando = False

    def _falar_streaming(self, texto: str):
        try:
            # ElevenLabs converte texto em PCM 16kHz
            audio_generator = self.client.text_to_speech.convert_as_stream(
                text=texto,
                voice_id=self.voice_id,
                model_id=self.model_id,
                output_format="pcm_16000",
                voice_settings=self.voice_settings
            )

            # Usar audio_lock para evitar colisão com AudioEngine
            with audio_lock:
                with sd.OutputStream(samplerate=16000, channels=1, dtype='int16') as stream:
                    self._stream = stream
                    for chunk in audio_generator:
                        if self._stop_event.is_set():
                            break
                        
                        if chunk:
                            audio_data = np.frombuffer(chunk, dtype=np.int16)
                            # Aplicar volume (Func 9)
                            if self.volume != 1.0:
                                audio_data = (audio_data.astype(np.float32) * self.volume).clip(-32768, 32767).astype(np.int16)
                            
                            stream.write(audio_data)
        except Exception as e:
            raise e

    def _fallback_local(self, texto: str):
        try:
            import pyttsx3
            import pythoncom
            
            pythoncom.CoInitialize()
            engine = pyttsx3.init()
            
            # Aplicar rate e volume (Func 9)
            engine.setProperty('rate', self.rate)
            engine.setProperty('volume', min(1.0, self.volume)) # pyttsx3 limita a 1.0
            
            voices = engine.getProperty('voices')
            lang_code = self.idioma.split('-')[0] # 'pt' de 'pt-PT'
            
            encontrou = False
            for v in voices:
                if lang_code in v.id.lower() or lang_code in v.name.lower():
                    engine.setProperty('voice', v.id)
                    encontrou = True
                    break
            
            if not encontrou and self.voice_id:
                engine.setProperty('voice', self.voice_id)
            
            # Dividir texto em frases para permitir interrupção entre cada uma
            frases = _re.split(r'(?<=[.!?;])\s+', texto)
            if not frases:
                frases = [texto]
            
            for frase in frases:
                if self._stop_event.is_set():
                    break
                if frase.strip():
                    engine.say(frase.strip())
                    engine.runAndWait()
            
            pythoncom.CoUninitialize()
        except Exception as e:
            console.print(f"[dim red]Falha crítica: Fallback local indisponível ({e}).[/dim red]")
