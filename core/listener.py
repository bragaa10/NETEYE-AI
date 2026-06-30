"""
NetEye — core/listener.py (WAKE WORD + VAD)
===========================================
Módulo de captura de microfone com:
1. Wake Word Detection (Ei NetEye) - Func 1
2. VAD (Voice Activity Detection) - webrtcvad
3. Echo Prevention Delay - Bug 2
4. Inactivity Watchdog - Bug 9
"""

import queue
import threading
import wave
import tempfile
import os
import time
import numpy as np
import sounddevice as sd
import webrtcvad
from rich.console import Console
from core.audio_engine import audio_engine

console = Console()

# Tentar importar openwakeword (opcional para evitar quebras se não estiver instalado)
try:
    from openwakeword.model import Model
    WAKEPWORD_AVAILABLE = True
except ImportError:
    WAKEPWORD_AVAILABLE = False


class Listener:
    SAMPLE_RATE = 16000      
    FRAME_DURATION = 30      
    CANAIS = 1               

    def __init__(self, config: dict):
        self.aggressividade = config.get("aggressividade", 2)
        self.silencio_max = config.get("silencio_para_processar", 0.8)   
        self.min_fala = config.get("tempo_minimo_fala", 0.3)             
        self.usar_wake_word = config.get("usar_wake_word", True)
        self.interromper_ao_falar = config.get("interromper_ao_falar", True)
        self._interrupt_count = 0  # FIX: Estado persistente entre chamadas. Inicializar aqui em vez de dentro do loop.

        self.frame_size = int(self.SAMPLE_RATE * self.FRAME_DURATION / 1000)

        self.vad = webrtcvad.Vad(self.aggressividade)
        self._audio_queue = queue.Queue()
        self._a_escutar = False
        self._stream = None
        self._active_listening = not self.usar_wake_word # Se não usar WW, está sempre ativo

        # Inicializar Wake Word Model (Ei NetEye)
        self.ww_model = None
        if self.usar_wake_word and WAKEPWORD_AVAILABLE:
            try:
                # Carregar modelos padrão (ou específicos se fornecidos)
                self.ww_model = Model(wakeword_models=["hey_neteye"], inference_framework="onnx")
                console.print("[dim green][OK] Wake Word ativada (Ei NetEye)[/dim green]")
            except Exception as e:
                console.print(f"[dim yellow]⚠️ Falha ao carregar Wake Word: {e}. Modo 'sempre escuta' ativo.[/dim yellow]")
                self._active_listening = True

    def iniciar(self):
        self._a_escutar = True
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CANAIS,
            dtype="int16",
            blocksize=self.frame_size,
            callback=self._callback_audio
        )
        self._stream.start()
        console.print(f"[dim]🎙️  Microfone ativo ({'Wake Word' if self.ww_model else 'Direto'}).[/dim]")

    def parar(self):
        self._a_escutar = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _get_vad_bytes(self, frame) -> bytes:
        frame_bytes = frame.tobytes()
        expected_len = self.frame_size * 2
        if len(frame_bytes) < expected_len:
            frame_bytes = frame_bytes.ljust(expected_len, b'\x00')
        elif len(frame_bytes) > expected_len:
            frame_bytes = frame_bytes[:expected_len]
        return frame_bytes

    def ouvir_comando(self, speaker=None, ignorar_wake_word=False, timeout=180.0) -> str | None:
        """
        Bloqueia até detetar wake word e depois uma fala completa.
        Suporta bypass de wake word e timeout personalizado.
        """
        frames_voz = []
        frames_silencio = 0
        a_gravar = False
        inicio_idle = time.time()

        # Resetar estado se estivermos a usar wake word e não for para ignorar
        if self.ww_model:
            if ignorar_wake_word:
                self._active_listening = True
            else:
                self._active_listening = False

        # Limpar queue
        while not self._audio_queue.empty():
            self._audio_queue.get_nowait()

        while True:
            # Watchdog/Timeout
            tempo_idle = time.time() - inicio_idle
            if not a_gravar and (tempo_idle > timeout):
                if timeout == 10.0:
                    return "TIMEOUT"
                return "TIMEOUT_IDLE"

            try:
                frame = self._audio_queue.get(timeout=2.0)
            except queue.Empty:
                continue

            # Echo Prevention com suporte a interrupção por voz
            if speaker and speaker.esta_a_falar():
                if self.interromper_ao_falar:
                    # Verificar se o utilizador está a tentar interromper (voz forte e contínua)
                    try:
                        frame_bytes = self._get_vad_bytes(frame)
                        tem_voz_forte = self.vad.is_speech(frame_bytes, self.SAMPLE_RATE)
                    except Exception:
                        tem_voz_forte = False
                    
                    if tem_voz_forte:
                        # Contar frames consecutivos de voz durante a fala do speaker
                        self._interrupt_count += 1
                        
                        # Se detetados 5+ frames consecutivos de voz (~150ms), interromper o speaker
                        if self._interrupt_count >= 5:
                            console.print("[bold yellow]⚡ Interrupção detetada — a silenciar speaker.[/bold yellow]")
                            speaker.parar()
                            self._interrupt_count = 0
                            a_gravar = False
                            frames_voz.clear()
                            inicio_idle = time.time()
                            continue
                    else:
                        self._interrupt_count = 0
                
                # Se não interrompeu (ou interrupção desativada), descartar frame (eco do speaker)
                a_gravar = False
                frames_voz.clear()
                inicio_idle = time.time()
                continue

            # --- FASE 1: ESPERAR WAKE WORD (se configurado) ---
            if not self._active_listening and self.ww_model:
                # openwakeword espera arrays numpy de float32
                audio_float = frame.astype(np.float32) / 32768.0
                prediction = self.ww_model.predict(audio_float)
                
                # Verificar se algum modelo disparou (threshold 0.5)
                ww_detected = False
                for model_name, prob in prediction.items():
                    if prob > 0.6: # Sensibilidade sénior
                        ww_detected = True
                        console.print(f"[bold green]✨ Wake Word detetada: {model_name} ({prob:.2f})[/bold green]")
                        break
                
                if ww_detected:
                    self._active_listening = True
                    audio_engine.play("mic_on") # Feedback Func 7
                    inicio_idle = time.time() # Reset idle
                continue # Próximo frame para começar a gravar

            # --- FASE 2: GRAVAR COMANDO (VAD) ---
            try:
                frame_bytes = self._get_vad_bytes(frame)
                tem_voz = self.vad.is_speech(frame_bytes, self.SAMPLE_RATE)
            except Exception:
                tem_voz = False

            if tem_voz:
                if not a_gravar:
                    a_gravar = True
                    frames_silencio = 0
                    console.print("[dim cyan](A ouvir comando...)[/dim cyan]")

                frames_voz.append(frame)
                frames_silencio = 0
                inicio_idle = time.time()

            elif a_gravar:
                frames_voz.append(frame)
                frames_silencio += 1

                # Parar se houver silêncio suficiente após fala
                if frames_silencio >= int(self.silencio_max * 1000 / self.FRAME_DURATION):
                    audio_engine.play("mic_off") # Feedback Func 7
                    break

        # Se capturou comando, volta para modo passivo na próxima chamada
        if len(frames_voz) < int(self.min_fala * 1000 / self.FRAME_DURATION):
            return None

        return self._guardar_wav(frames_voz)

    def _callback_audio(self, indata, frames, time_info, status):
        if self._a_escutar:
            self._audio_queue.put(indata[:, 0].copy())

    def _guardar_wav(self, frames: list) -> str | None:
        tmp_path = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="NetEye_cmd_")
            tmp_path = tmp.name
            tmp.close()
            audio_data = np.concatenate(frames, axis=0)
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(self.CANAIS)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(audio_data.tobytes())
            return tmp_path
        except Exception as e:
            console.print(f"[red]Erro ao guardar áudio: {e}[/red]")
            if tmp_path and os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except Exception: pass
            return None
