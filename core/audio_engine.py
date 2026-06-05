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

class AudioEngine:
    """
    Motor de áudio simples para sons de interface (WAV).
    """
    
    def __init__(self):
        self.base_path = os.path.join(os.path.dirname(__file__), "..", "assets", "sounds")
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path, exist_ok=True)
            console.print(f"[dim yellow]Caminho de sons criado: {self.base_path}[/dim yellow]")

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
            with wave.open(path, "rb") as wf:
                params = wf.getparams()
                frames = wf.readframes(params.nframes)
                audio_data = np.frombuffer(frames, dtype=np.int16)
                
                # Normalizar para float32 se necessário ou usar int16 diretamente
                sd.play(audio_data, samplerate=params.framerate, blocking=False)
                # O sd.play não bloqueia, mas a thread termina logo. 
                # Precisamos de esperar que o som termine ou usar sd.wait()
                sd.wait()
        except Exception as e:
            console.print(f"[dim red]Erro ao tocar som {os.path.basename(path)}: {e}[/dim red]")

# Instância global para uso fácil
audio_engine = AudioEngine()
