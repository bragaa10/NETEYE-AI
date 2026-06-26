"""
NetEye — core/audio_engine.py (Func 7)
======================================
Gere a reprodução de efeitos sonoros (SFX) do sistema.
Utiliza sounddevice para reprodução não bloqueante.
"""

import os
import threading
import wave
import numpy as np
import sounddevice as sd
from rich.console import Console

console = Console()

# Locks separados para evitar deadlock entre SFX e TTS
_sfx_lock = threading.Lock()  # FIX: Lock exclusivo para SFX, não partilhado com TTS.
audio_lock = _sfx_lock  # Compatibilidade com código existente

class AudioEngine:
    """
    Motor de áudio simples para sons de interface (WAV).
    """
    
    def __init__(self):
        self.base_path = os.path.join(os.path.dirname(__file__), "..", "assets", "sounds")
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path, exist_ok=True)
            console.print(f"[dim yellow]Caminho de sons criado: {self.base_path}[/dim yellow]")
        
        # Gerar beeps padrão se não existirem
        self._gerar_beep("mic_on", [880], 0.08)
        self._gerar_beep("mic_off", [440], 0.08)
        self._gerar_beep("system_ready", [550, 880], 0.15)

    def _gerar_beep(self, nome: str, frequencias: list, duracao: float = 0.1, sample_rate: int = 16000):
        path = os.path.join(self.base_path, f"{nome}.wav")
        if os.path.exists(path):
            return
        try:
            t = np.linspace(0, duracao, int(sample_rate * duracao), False)
            if len(frequencias) == 1:
                audio_data = np.sin(2 * np.pi * frequencias[0] * t)
                decay = np.exp(-5 * t / duracao)
                audio_data = audio_data * decay
            else:
                n_tons = len(frequencias)
                duracao_tom = duracao / n_tons
                segmentos = []
                for freq in frequencias:
                    t_tom = np.linspace(0, duracao_tom, int(sample_rate * duracao_tom), False)
                    tom_data = np.sin(2 * np.pi * freq * t_tom)
                    decay_tom = np.exp(-5 * t_tom / duracao_tom)
                    segmentos.append(tom_data * decay_tom)
                audio_data = np.concatenate(segmentos)
            
            audio_data = (audio_data * 16384).astype(np.int16)
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data.tobytes())
            console.print(f"[dim green][OK] Som sintetizado gerado: {nome}.wav[/dim green]")
        except Exception as e:
            console.print(f"[dim red]Erro ao gerar som {nome}: {e}[/dim red]")

    def play(self, sound_name: str):
        """
        Reproduz um som da pasta assets/sounds em background.
        Ex: play("mic_on") procura por assets/sounds/mic_on.wav
        """
        path = os.path.join(self.base_path, f"{sound_name}.wav")
        if not os.path.exists(path):
            # Se não existir, falha silenciosamente ou loga
            return

        threading.Thread(target=self._play_wav, args=(path,), daemon=True).start()

    def _play_wav(self, path: str):
        """Lógica interna de reprodução WAV."""
        try:
            with audio_lock:
                with wave.open(path, "rb") as wf:
                    params = wf.getparams()
                    frames = wf.readframes(params.nframes)
                    audio_data = np.frombuffer(frames, dtype=np.int16)
                    # FIX: blocking=True é correto. Já estamos numa thread daemon própria.
                    # blocking=False + sd.wait() é equivalente mas propenso a race conditions.
                    sd.play(audio_data, samplerate=params.framerate, blocking=True)
        except Exception as e:
            console.print(f"[dim red]Erro ao tocar som {os.path.basename(path)}: {e}[/dim red]")

# Instância global para uso fácil
audio_engine = AudioEngine()
