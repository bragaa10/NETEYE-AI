"""
NetEye — core/transcriber.py
=============================
Transcrição de voz com faster-whisper.
Otimizado para Português de Portugal em contexto de navegação web.
"""

import os
import time
import wave
import json
import re
import threading
import numpy as np
from faster_whisper import WhisperModel
from rich.console import Console

console = Console()

# Carregar correções fonéticas do synonyms.json
_SYNONYMS_PATH = os.path.join(os.path.dirname(__file__), "..", "synonyms.json")
_CORRECOES: dict[str, str] = {}
try:
    with open(_SYNONYMS_PATH, encoding="utf-8") as f:
        dados = json.load(f)
        _CORRECOES = dados.get("_correcoes_foneticas", {})
except Exception:
    pass


def _aplicar_correcoes(texto: str) -> str:
    """Aplica correções fonéticas ao texto transcrito pelo Whisper."""
    import re as _re
    t = texto.lower().strip()

    if t in _CORRECOES:
        resultado = _CORRECOES[t]
        if texto and texto[0].isupper() and resultado:
            return resultado[0].upper() + resultado[1:]
        return resultado

    for errado, certo in sorted(_CORRECOES.items(), key=lambda x: -len(x[0])):
        padrao = r'(?<!\w)' + _re.escape(errado) + r'(?!\w)'
        if _re.search(padrao, t):
            t = _re.sub(padrao, certo, t)

    if texto and texto[0].isupper() and t:
        t = t[0].upper() + t[1:]
    return t


class Transcriber:
    def __init__(self, config: dict):
        modelo     = config.get("modelo_whisper", "small")
        dispositivo = config.get("dispositivo", "cpu")
        self.idioma = config.get("idioma_whisper", "pt")
        self.modelo = None

        compute_type = "int8" if dispositivo == "cpu" else "float16"
        console.print(f"[dim]⏳ A carregar faster-whisper '{modelo}' [{compute_type}]...[/dim]")

        # Bug 6: Inicializar com timeout compatível com Windows (Thread join)
        init_res = {"model": None, "error": None}

        def _init_model():
            try:
                init_res["model"] = WhisperModel(
                    modelo,
                    device=dispositivo,
                    compute_type=compute_type,
                    cpu_threads=4,
                    num_workers=1,
                    download_root="./models",
                )
            except Exception as e:
                init_res["error"] = e

        thread = threading.Thread(target=_init_model, daemon=True)
        thread.start()
        thread.join(timeout=60.0)

        if thread.is_alive():
            console.print(f"[yellow]⚠ Timeout ao carregar faster-whisper (60s). O carregamento continuará em background.[/yellow]")
            # O modelo poderá ficar disponível mais tarde se o download terminar
        elif init_res["error"]:
            console.print(f"[yellow]⚠ Erro ao carregar faster-whisper: {init_res['error']}.[/yellow]")
        else:
            self.modelo = init_res["model"]
            console.print(f"[dim green]✓ faster-whisper '{modelo}' pronto.[/dim green]")

    def transcrever(self, caminho_audio: str) -> str:
        if not self.modelo:
            return ""
            
        if not caminho_audio or not os.path.exists(caminho_audio):
            return ""

        try:
            inicio = time.time()
            audio = self._carregar_wav(caminho_audio)
            if audio is None: return ""

            duracao_audio = len(audio) / 16000
            if duracao_audio < 0.5: return ""

            resultado = {"segmentos": None, "erro": None}
            
            def _transcrever():
                try:
                    segmentos, info = self.modelo.transcribe(
                        audio,
                        language=self.idioma,
                        beam_size=1,
                        temperature=0.0,
                        condition_on_previous_text=False,
                        initial_prompt=(
                            "Assistente de navegação web. Comandos em português de Portugal: "
                            "abrir YouTube, pesquisar no Google, aceitar tudo, rejeitar tudo, "
                            "voltar atrás, descer a página, clicar em entrar, sim, não, por favor."
                        ),
                        compression_ratio_threshold=2.2,
                        log_prob_threshold=-0.6,
                        no_speech_threshold=0.5,
                        vad_filter=True,
                        vad_parameters=dict(
                            min_silence_duration_ms=400,
                            speech_pad_ms=500,
                            threshold=0.45,
                        ),
                    )
                    resultado["segmentos"] = segmentos
                except Exception as e:
                    resultado["erro"] = e
            
            thread = threading.Thread(target=_transcrever, daemon=False)
            thread.start()
            thread.join(timeout=30.0)
            
            if thread.is_alive():
                console.print("[bold red]⚠️ Timeout na transcrição (>30s)[/bold red]")
                return ""
            
            if resultado["erro"]: raise resultado["erro"]
            
            segmentos = resultado["segmentos"]
            if segmentos is None: return ""

            texto_segments = " ".join(seg.text for seg in segmentos).strip()
            texto = _aplicar_correcoes(texto_segments) if texto_segments else ""
            duracao = time.time() - inicio

            if texto:
                console.print(f"[dim]🗣️  ({duracao:.1f}s): [bold white]{texto}[/bold white][/dim]")

            try:
                os.unlink(caminho_audio)
            except: pass

            return texto

        except Exception as e:
            console.print(f"[red]Erro na transcrição: {e}[/red]")
            return ""

    def _carregar_wav(self, caminho: str) -> np.ndarray | None:
        try:
            with wave.open(caminho, "rb") as wf:
                frames      = wf.readframes(wf.getnframes())
                sample_rate = wf.getframerate()
                n_channels  = wf.getnchannels()
                sampwidth   = wf.getsampwidth()

            dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
            dtype = dtype_map.get(sampwidth, np.int16)
            audio = np.frombuffer(frames, dtype=dtype).astype(np.float32)

            if n_channels > 1:
                audio = audio.reshape(-1, n_channels).mean(axis=1)

            max_val = float(np.iinfo(dtype).max)
            audio   = audio / max_val

            if sample_rate != 16000:
                try:
                    import scipy.signal as signal
                    num_samples = int(len(audio) * 16000 / sample_rate)
                    audio = signal.resample(audio, num_samples)
                except ImportError: pass

            return audio.astype(np.float32)

        except Exception as e:
            console.print(f"[red]Erro ao carregar WAV: {e}[/red]")
            return None