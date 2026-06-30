"""
NetEye — core/vision.py (VISÃO SÉNIOR / OCR)
===========================================
Fallback de visão computacional para páginas que não são acessíveis via DOM.
Usa EasyOCR para extrair texto de screenshots.
Thread-safe singleton loader.
"""

import os
import tempfile
import threading
import cv2
import numpy as np
import mss
import mss.tools
from PIL import Image
from rich.console import Console

console = Console()

_ocr_reader = None
_ocr_lock = threading.Lock()

def _obter_reader():
    """Carrega o EasyOCR de forma thread-safe apenas quando necessário."""
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_lock:
            if _ocr_reader is None:
                console.print("[dim]⏳ A carregar EasyOCR (primeira vez demora)...[/dim]")
                import easyocr
                # gpu=False garante compatibilidade máxima sem CUDA
                _ocr_reader = easyocr.Reader(["pt", "en"], gpu=False, verbose=False)
                console.print("[dim green][OK] EasyOCR carregado.[/dim green]")
    return _ocr_reader


class Vision:
    """
    Captura e analisa visualmente o ecrã quando DOM não é suficiente.
    """

    def __init__(self):
        self._sct = mss.mss()
        self._lock = threading.Lock()

    def capturar_ecra(self) -> str | None:
        """
        Tira um screenshot do ecrã FÍSICO e guarda num ficheiro temporário.
        AVISO: este método captura o monitor inteiro, não a página do browser.
        Só deve ser usado como último recurso quando não há acesso direto ao
        browser (ex: diagnóstico do sistema operativo). Para ler o conteúdo da
        página web, usa sempre extrair_texto_de_bytes() com o screenshot do
        Playwright, nunca este método.
        """
        try:
            with self._lock:
                monitor = self._sct.monitors[1]  # Monitor principal
                screenshot = self._sct.grab(monitor)

                tmp = tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False, prefix="NetEye_screen_"
                )
                tmp_path = tmp.name
                tmp.close()

                mss.tools.to_png(screenshot.rgb, screenshot.size, output=tmp_path)
                return tmp_path
        except Exception as e:
            console.print(f"[red]Erro ao capturar ecrã: {e}[/red]")
            return None

    def extrair_texto_de_bytes(self, imagem_bytes: bytes) -> str:
        """
        FIX CRÍTICO: Extrai texto diretamente dos bytes de um screenshot já
        capturado (ex: o JPEG do Playwright via browser.tirar_screenshot()).
        Isto garante que o OCR lê SEMPRE o conteúdo real da página web que o
        NetEye está a controlar, em vez de capturar o ecrã físico inteiro do
        monitor (que pode mostrar outras janelas, o ambiente de trabalho, ou
        nada relacionado com a página atual se o browser não estiver em foco
        ou estiver a correr em modo headless).
        """
        if not imagem_bytes:
            return ""
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, prefix="NetEye_pagescreen_")
            tmp_path = tmp.name
            tmp.write(imagem_bytes)
            tmp.close()
            return self.extrair_texto_screenshot(tmp_path)
        except Exception as e:
            console.print(f"[red]Erro ao processar screenshot da página para OCR: {e}[/red]")
            return f"[FALHA NO DIAGNÓSTICO: não foi possível processar o screenshot da página: {e}]"

    def extrair_texto_screenshot(self, caminho_imagem: str = None) -> str:
        """
        Extrai texto de um screenshot usando EasyOCR.
        Se caminho_imagem for None, captura o ecrã FÍSICO automaticamente
        (comportamento legado, use extrair_texto_de_bytes para ler a página web).
        """
        if not caminho_imagem:
            caminho_imagem = self.capturar_ecra()
            if not caminho_imagem:
                return ""

        tmp_proc = caminho_imagem.replace(".png", "_proc.png").replace(".jpg", "_proc.png")
        try:
            reader = _obter_reader()

            # Pré-processar imagem para melhor OCR
            imagem = cv2.imread(caminho_imagem)
            if imagem is None:
                console.print(f"[red]Erro: Impossível ler imagem {caminho_imagem}[/red]")
                return ""
            imagem_cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
            _, imagem_bin = cv2.threshold(
                imagem_cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            # Guardar imagem processada
            cv2.imwrite(tmp_proc, imagem_bin)

            # Executar OCR
            resultados = reader.readtext(tmp_proc, detail=1, paragraph=True)

            # Filtrar e ordenar por posição vertical (cima→baixo)
            textos = []
            for item in resultados:
                if len(item) == 3:
                    bbox, texto, confianca = item
                elif len(item) == 2:
                    bbox, texto = item
                    confianca = 1.0  # default confidence when paragraph mode omits it
                else:
                    continue

                texto_str = str(texto).strip()
                if confianca > 0.3 and len(texto_str) > 1:
                    try:
                        y = bbox[0][1]
                    except (IndexError, TypeError):
                        y = 0
                    textos.append((y, texto_str))  # (y, texto)

            if not textos:
                return "Nenhum texto visível detetado no ecrã via OCR."

            textos.sort(key=lambda x: x[0])
            resultado = "\n".join(t[1] for t in textos)
            if len(resultado) > 1500:
                resultado = resultado[:1500] + "\n[Conteúdo OCR truncado para economizar recursos]"

            return resultado

        except Exception as e:
            console.print(f"[bold red]Erro crítico no OCR: {e}[/bold red]")
            return f"[FALHA NO DIAGNÓSTICO: Ocorreu um erro ao tentar processar o ecrã via OCR: {e}]"
        finally:
            # Limpar ficheiros temporários
            for f in [caminho_imagem, tmp_proc]:
                try:
                    if os.path.exists(f):
                        os.unlink(f)
                except Exception:
                    pass

    def pagina_tem_conteudo_visual(self, html: str) -> bool:
        """
        Verifica se a página tem conteúdo que só é acessível visualmente.
        """
        indicadores = [
            "canvas", "captcha", "recaptcha",
            "application/pdf", "embed", "object"
        ]
        html_lower = html.lower()
        return any(ind in html_lower for ind in indicadores)