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

        init_res = {"error": None}

        def _init_model():
            try:
                self.modelo = WhisperModel(
                    modelo,
                    device=dispositivo,
                    compute_type=compute_type,
                    cpu_threads=4,
                    num_workers=1,
                    download_root="./models",
                )
                console.print(f"[dim green][OK] faster-whisper '{modelo}' pronto.[/dim green]")
            except Exception as e:
                init_res["error"] = e
                console.print(f"[yellow]⚠ Erro ao carregar faster-whisper: {e}.[/yellow]")

        self.thread_init = threading.Thread(target=_init_model, daemon=True)
        self.thread_init.start()
        # Dar tolerância curta no startup
        self.thread_init.join(timeout=0.5)

    def transcrever(self, caminho_audio: str, fast: bool = False) -> str:
        if not caminho_audio or not os.path.exists(caminho_audio):
            return ""

        if not self.modelo:
            if hasattr(self, "thread_init") and self.thread_init.is_alive():
                try: os.unlink(caminho_audio)
                except Exception: pass
                return "MODELO_CARREGANDO"
            try: os.unlink(caminho_audio)
            except Exception: pass
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
                    if fast:
                        # Modo ultra-rápido para resposta de sim/não
                        segmentos, info = self.modelo.transcribe(
                            audio,
                            language=self.idioma,
                            beam_size=1,
                            temperature=0.0,
                            condition_on_previous_text=False,
                            initial_prompt="sim. não.",
                            max_new_tokens=5,
                            vad_filter=True,
                            vad_parameters=dict(
                                min_silence_duration_ms=200,
                                speech_pad_ms=200,
                                threshold=0.5,
                            ),
                        )
                    else:
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
                    # Consumir o generator no worker thread para processar o áudio lá
                    resultado["segmentos"] = list(segmentos) if segmentos is not None else None
                except Exception as e:
                    resultado["erro"] = e
            
            thread = threading.Thread(target=_transcrever, daemon=True)
            thread.start()
            thread.join(timeout=5.0 if fast else 30.0)
            
            if thread.is_alive():
                console.print(f"[bold red]⚠️ Timeout na transcrição {'rápida' if fast else ''} (>30s)[/bold red]")
                return ""
            
            if resultado["erro"]: raise resultado["erro"]
            
            segmentos = resultado["segmentos"]
            if segmentos is None: return ""

            texto_segments = " ".join(seg.text for seg in segmentos).strip()
            texto = _aplicar_correcoes(texto_segments) if texto_segments else ""
            duracao = time.time() - inicio

            if texto:
                console.print(f"[dim]🗣️  ({duracao:.1f}s): [bold white]{texto}[/bold white][/dim]")

            return texto

        except Exception as e:
            console.print(f"[red]Erro na transcrição: {e}[/red]")
            return ""
        finally:
            try:
                if os.path.exists(caminho_audio):
                    os.unlink(caminho_audio)
            except Exception: pass

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