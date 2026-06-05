"""
log_terminal.py — Widget terminal de logs thread-safe
Usa Queue + after() para receber linhas do subprocesso sem bloquear a UI
"""
import queue
import customtkinter as ctk
from gui.theme import SURFACE_2, ACCENT_HOV, TEXT_2, GREEN, RED, AMBER, FONT_MONO, BORDER


class LogTerminal(ctk.CTkFrame):
    """
    Terminal de logs estilo dashboard.html.
    Recebe linhas via .append(line) de qualquer thread.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=SURFACE_2, corner_radius=12, **kwargs)
        self._queue: queue.Queue = queue.Queue()
        self._build()
        self._poll()

    # ── Layout ──────────────────────────────────────────────────────────────
    def _build(self):
        # Cabeçalho
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 0))

        ctk.CTkLabel(
            header, text="Terminal de Logs",
            font=("Segoe UI", 10, "bold"),
            text_color=ACCENT_HOV
        ).pack(side="left")

        ctk.CTkButton(
            header, text="Limpar",
            width=60, height=26,
            font=("Segoe UI", 9),
            fg_color=BORDER,
            hover_color="#1e2d4a",
            command=self.clear
        ).pack(side="right")

        # Separador
        sep = ctk.CTkFrame(self, height=1, fg_color=BORDER)
        sep.pack(fill="x", padx=14, pady=(10, 0))

        # Textbox
        self.textbox = ctk.CTkTextbox(
            self,
            font=FONT_MONO,
            fg_color="transparent",
            text_color=TEXT_2,
            border_width=0,
            wrap="word",
            state="disabled",
        )
        self.textbox.pack(fill="both", expand=True, padx=14, pady=(8, 12))

        # Tags de cor
        self.textbox._textbox.tag_config("system",  foreground=ACCENT_HOV)
        self.textbox._textbox.tag_config("success", foreground=GREEN)
        self.textbox._textbox.tag_config("error",   foreground=RED)
        self.textbox._textbox.tag_config("warn",    foreground=AMBER)
        self.textbox._textbox.tag_config("normal",  foreground=TEXT_2)

    # ── API Pública ──────────────────────────────────────────────────────────
    def append(self, text: str, tag: str = "normal"):
        """Thread-safe: adiciona linha à queue."""
        self._queue.put((text, tag))

    def clear(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")

    def system(self, text: str):
        self.append(f"[SYS] {text}", "system")

    def success(self, text: str):
        self.append(f"[OK]  {text}", "success")

    def error(self, text: str):
        self.append(f"[ERR] {text}", "error")

    # ── Polling interno ──────────────────────────────────────────────────────
    def _poll(self):
        """Drena a queue e escreve no textbox (executa na thread principal)."""
        try:
            while True:
                text, tag = self._queue.get_nowait()
                self.textbox.configure(state="normal")
                self.textbox._textbox.insert("end", text + "\n", tag)
                self.textbox.see("end")
                self.textbox.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._poll)
