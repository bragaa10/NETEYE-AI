"""
NetEye — core/vision.py
========================
Fallback de visão computacional para páginas que não são acessíveis via DOM.

Usa EasyOCR para extrair texto de screenshots.
Útil para: PDFs no browser, CAPTCHAs, aplicações canvas, imagens com texto.
"""

import os
import tempfile
import mss
import mss.tools
import cv2
import numpy as np
from PIL import Image
from rich.console import Console

console = Console()

# EasyOCR é importado de forma lazy (demorada a carregar)
_ocr_reader = None


def _obter_reader():
    """Carrega o EasyOCR apenas quando necessário."""
    global _ocr_reader
    if _ocr_reader is None:
        console.print("[dim]⏳ A carregar EasyOCR (primeira vez demora)...[/dim]")
        import easyocr
        _ocr_reader = easyocr.Reader(["pt", "en"], gpu=False, verbose=False)
        console.print("[dim green]✓ EasyOCR carregado.[/dim green]")
    return _ocr_reader


class Vision:
    """
    Captura e analisa visualmente o ecrã quando DOM não é suficiente.
    """

    def __init__(self):
        self._sct = mss.mss()

    # ------------------------------------------------------------------
    # API PÚBLICA
    # ------------------------------------------------------------------

    def capturar_ecra(self) -> str | None:
        """
        Tira um screenshot do ecrã e guarda num ficheiro temporário.
        Retorna o caminho do ficheiro PNG.
        """
        try:
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

    def extrair_texto_screenshot(self, caminho_imagem: str = None) -> str:
        """
        Extrai texto de um screenshot usando EasyOCR.
        Se caminho_imagem for None, captura o ecrã automaticamente.
        """
        if not caminho_imagem:
            caminho_imagem = self.capturar_ecra()
            if not caminho_imagem:
                return ""

        try:
            reader = _obter_reader()

            # Pré-processar imagem para melhor OCR
            imagem = cv2.imread(caminho_imagem)
            imagem_cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
            _, imagem_bin = cv2.threshold(
                imagem_cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            # Guardar imagem processada
            tmp_proc = caminho_imagem.replace(".png", "_proc.png")
            cv2.imwrite(tmp_proc, imagem_bin)

            # Executar OCR
            resultados = reader.readtext(tmp_proc, detail=1, paragraph=True)

            # Filtrar e ordenar por posição vertical (cima→baixo)
            textos = []
            for (bbox, texto, confianca) in resultados:
                if confianca > 0.3 and len(texto.strip()) > 1:
                    textos.append((bbox[0][1], texto.strip()))  # (y, texto)

            textos.sort(key=lambda x: x[0])
            resultado = "\n".join(t[1] for t in textos)

            # Limpar ficheiros temporários
            for f in [caminho_imagem, tmp_proc]:
                try:
                    os.unlink(f)
                except Exception:
                    pass

            return resultado

        except Exception as e:
            console.print(f"[red]Erro no OCR: {e}[/red]")
            return ""

    def pagina_tem_conteudo_visual(self, html: str) -> bool:
        """
        Verifica se a página tem conteúdo que só é acessível visualmente.
        (CAPTCHAs, canvas, PDFs embedidos, etc.)
        """
        indicadores = [
            "canvas", "captcha", "recaptcha",
            "application/pdf", "embed", "object"
        ]
        html_lower = html.lower()
        return any(ind in html_lower for ind in indicadores)
