"""
dashboard_view.py — Painel de Controlo
Equivalente a dashboard.html
"""
import os
import sys
import subprocess
import threading
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from gui.theme import (
    BG, SURFACE, SURFACE_2, SURFACE_3, ACCENT, ACCENT_HOV, ACCENT_GLOW,
    GREEN, GREEN_DIM, RED, TEXT_1, TEXT_2, TEXT_3, BORDER,
    FONT_H2, FONT_H3, FONT_BODY, FONT_BOLD, FONT_BODY_SM, FONT_STAT
)
from gui.widgets.log_terminal import LogTerminal


class DashboardView(ctk.CTkFrame):
    """
    Painel de controlo principal com:
    - Status (Microfone, API, Browser)
    - Estatísticas (Comandos, Favoritos, Bloqueados)
    - Terminal de Logs
    - Tabela últimos 10 comandos
    - Botão Iniciar/Parar NetEye
    """

    def __init__(self, master, db, user_id: int, **kwargs):
        super().__init__(master, fg_color=BG, corner_radius=0, **kwargs)
        self.db = db
        self.user_id = user_id
        self._process: subprocess.Popen | None = None
        self._log_thread: threading.Thread | None = None
        self._build()

        # Auto-iniciar assistente após breve delay para UI estabilizar
        self.after(500, self._start_assistant)

    # ── Construção UI ────────────────────────────────────────────────────────
    def _build(self):
        # Scroll container
        scroll = ctk.CTkScrollableFrame(self, fg_color=BG, scrollbar_button_color=BORDER)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Cabeçalho ────────────────────────────────────────────────────
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 0))

        left_h = ctk.CTkFrame(header, fg_color="transparent")
        left_h.pack(side="left")
        ctk.CTkLabel(left_h, text="Painel de Controlo", font=FONT_H2, text_color=TEXT_1).pack(anchor="w")
        ctk.CTkLabel(left_h, text="Monitorização em tempo real do NetEye", font=FONT_BODY_SM, text_color=TEXT_3).pack(anchor="w")

        right_h = ctk.CTkFrame(header, fg_color="transparent")
        right_h.pack(side="right")

        self.btn_toggle = ctk.CTkButton(
            right_h, text="▶  Iniciar NetEye",
            height=40, width=170, corner_radius=8,
            font=FONT_BOLD,
            fg_color=ACCENT, hover_color="#3b7eef",
            command=self._toggle_assistant
        )
        self.btn_toggle.pack(side="left", padx=(0, 10))

        self.lbl_status_run = ctk.CTkLabel(
            right_h, text="⬤  Parado",
            font=FONT_BODY_SM, text_color=TEXT_3
        )
        self.lbl_status_run.pack(side="left")

        # ── Linha 1: Status + Stats ──────────────────────────────────────
        row1 = ctk.CTkFrame(scroll, fg_color="transparent")
        row1.pack(fill="x", padx=24, pady=(20, 0))
        row1.columnconfigure(0, weight=2)
        row1.columnconfigure(1, weight=3)

        self._build_status_panel(row1)
        self._build_stats_panel(row1)

        # ── Linha 2: Terminal + Tabela ───────────────────────────────────
        row2 = ctk.CTkFrame(scroll, fg_color="transparent")
        row2.pack(fill="x", padx=24, pady=(16, 24))
        row2.columnconfigure(0, weight=3)
        row2.columnconfigure(1, weight=2)

        self._build_terminal(row2)
        self._build_recent_table(row2)

    def _build_status_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)

        ctk.CTkLabel(card, text="Estado do Sistema", font=FONT_H3, text_color=TEXT_2).pack(anchor="w", padx=18, pady=(14, 8))
        sep = ctk.CTkFrame(card, height=1, fg_color=BORDER)
        sep.pack(fill="x", padx=18)

        self._status_dots = {}
        self._status_vals = {}
        for key, label, init_val, is_online in [
            ("mic",     "Microfone",      "Inativo",  False),
            ("api",     "Anthropic API",  "Online",   True),
            ("browser", "Browser",        "Fechado",  False),
        ]:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=8)

            dot_color = GREEN if is_online else SURFACE_3
            dot = ctk.CTkFrame(row, width=12, height=12, corner_radius=6, fg_color=dot_color)
            dot.pack(side="left", padx=(0, 12))
            dot.pack_propagate(False)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left")
            ctk.CTkLabel(info, text=label, font=FONT_BODY_SM, text_color=TEXT_2).pack(anchor="w")
            val_lbl = ctk.CTkLabel(info, text=init_val, font=FONT_BOLD, text_color=TEXT_1)
            val_lbl.pack(anchor="w")

            self._status_dots[key] = dot
            self._status_vals[key] = val_lbl

    def _build_stats_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)

        ctk.CTkLabel(card, text="Estatísticas", font=FONT_H3, text_color=TEXT_2).pack(anchor="w", padx=18, pady=(14, 8))
        sep = ctk.CTkFrame(card, height=1, fg_color=BORDER)
        sep.pack(fill="x", padx=18)

        stats_row = ctk.CTkFrame(card, fg_color="transparent")
        stats_row.pack(fill="both", expand=True, padx=18, pady=16)
        stats_row.columnconfigure((0, 1, 2), weight=1)

        stats = self._load_stats()
        labels = [
            ("comandos",  "Comandos Totais"),
            ("favoritos", "Favoritos"),
            ("bloqueados","Bloqueados"),
        ]
        self._stat_labels = {}
        for i, (key, title) in enumerate(labels):
            box = ctk.CTkFrame(stats_row, fg_color=SURFACE_2, corner_radius=10, border_width=1, border_color=BORDER)
            box.grid(row=0, column=i, padx=6, sticky="nsew")
            box.rowconfigure(0, weight=1)

            num = ctk.CTkLabel(box, text=str(stats.get(key, 0)), font=FONT_STAT, text_color=TEXT_1)
            num.pack(pady=(18, 2))
            ctk.CTkLabel(box, text=title, font=FONT_BODY_SM, text_color=TEXT_2).pack(pady=(0, 16))
            self._stat_labels[key] = num

    def _build_terminal(self, parent):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        card.rowconfigure(0, weight=1)

        self.terminal = LogTerminal(card)
        self.terminal.pack(fill="both", expand=True, padx=0, pady=0)
        self.terminal.system("Aguardando início do assistente...")

    def _build_recent_table(self, parent):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)

        ctk.CTkLabel(card, text="Últimos 10 Comandos", font=FONT_H3, text_color=TEXT_1).pack(anchor="w", padx=18, pady=(14, 8))
        sep = ctk.CTkFrame(card, height=1, fg_color=BORDER)
        sep.pack(fill="x", padx=18)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dark.Treeview",
            background=SURFACE, foreground=TEXT_1,
            fieldbackground=SURFACE, borderwidth=0,
            rowheight=28, font=("Segoe UI", 9)
        )
        style.configure("Dark.Treeview.Heading",
            background=SURFACE_2, foreground=TEXT_2,
            font=("Segoe UI", 9, "bold"), relief="flat"
        )
        style.map("Dark.Treeview", background=[("selected", ACCENT_GLOW)], foreground=[("selected", ACCENT_HOV)])

        tree_frame = tk.Frame(card, bg=SURFACE)
        tree_frame.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        self.tree_recent = ttk.Treeview(
            tree_frame, style="Dark.Treeview",
            columns=("hora", "titulo", "url"),
            show="headings", height=10
        )
        self.tree_recent.heading("hora",   text="Hora")
        self.tree_recent.heading("titulo", text="Comando / Título")
        self.tree_recent.heading("url",    text="URL")
        self.tree_recent.column("hora",   width=55,  stretch=False)
        self.tree_recent.column("titulo", width=130, stretch=True)
        self.tree_recent.column("url",    width=160, stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_recent.yview)
        self.tree_recent.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree_recent.pack(fill="both", expand=True)

        self._refresh_recent()

    # ── Dados ────────────────────────────────────────────────────────────────
    def _load_stats(self) -> dict:
        return {
            "comandos":  len(self.db.historico_completo(self.user_id)),
            "favoritos": len(self.db.listar_favoritos(self.user_id)),
            "bloqueados": len(self.db.listar_bloqueios(id_utilizador=self.user_id)),
        }

    def refresh(self):
        """Recarrega estatísticas e tabela de comandos recentes."""
        stats = self._load_stats()
        for key, lbl in self._stat_labels.items():
            lbl.configure(text=str(stats.get(key, 0)))
        self._refresh_recent()

    def _refresh_recent(self):
        for row in self.tree_recent.get_children():
            self.tree_recent.delete(row)
        recent = self.db.historico_recente(self.user_id, limite=10)
        if recent:
            for item in recent:
                hora = item.get("data_visita", "")[-8:-3] if item.get("data_visita") else ""
                titulo = item.get("titulo") or "Navegação"
                url = item.get("url", "")
                self.tree_recent.insert("", "end", values=(hora, titulo, url))
        else:
            self.tree_recent.insert("", "end", values=("—", "Nenhum comando registado", ""))

    # ── Assistente ───────────────────────────────────────────────────────────
    def _toggle_assistant(self):
        if self._process and self._process.poll() is None:
            self._stop_assistant()
        else:
            self._start_assistant()

    def _start_assistant(self):
        api_key = self.db.obter_configuracao(self.user_id, "api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key or not api_key.strip():
            self.terminal.error("Configure a chave API em Configurações primeiro.")
            return

        headless = self.db.obter_configuracao(self.user_id, "modo_headless", "False") == "True"
        if getattr(sys, 'frozen', False):
            # No modo executável (PyInstaller)
            cmd = [sys.executable]
        else:
            # No modo script (Python)
            # Garantir que usamos o script run_gui.py como entrada
            run_gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "run_gui.py")
            cmd = [sys.executable, run_gui_path]

        cmd += ["--assistant", "--user-id", str(self.user_id)]
        if headless:
            cmd.append("--headless")

        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", bufsize=1,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "ANTHROPIC_API_KEY": api_key}
            )
            self.btn_toggle.configure(text="■  Parar NetEye", fg_color="#8b1a1a", hover_color="#a52020")
            self.lbl_status_run.configure(text="⬤  Em execução", text_color=GREEN)
            self._status_dots["mic"].configure(fg_color=GREEN)
            self._status_vals["mic"].configure(text="Ativo")
            self.terminal.system("Assistente iniciado.")
            self._start_log_thread()
        except Exception as e:
            self.terminal.error(f"Erro ao iniciar: {e}")

    def _stop_assistant(self):
        if self._process:
            self._process.terminate()
            self._process = None
        self.btn_toggle.configure(text="▶  Iniciar NetEye", fg_color=ACCENT, hover_color="#3b7eef")
        self.lbl_status_run.configure(text="⬤  Parado", text_color=TEXT_3)
        self._status_dots["mic"].configure(fg_color=SURFACE_3)
        self._status_vals["mic"].configure(text="Inativo")
        self._status_dots["browser"].configure(fg_color=SURFACE_3)
        self._status_vals["browser"].configure(text="Fechado")
        self.terminal.system("Assistente parado.")

    def _start_log_thread(self):
        def reader():
            while self._process and self._process.poll() is None:
                line = self._process.stdout.readline()
                if line:
                    txt = line.strip()
                    tag = "normal"
                    if any(k in txt.lower() for k in ("erro", "error", "exception")):
                        tag = "error"
                    elif any(k in txt.lower() for k in ("ok", "sucesso", "abri")):
                        tag = "success"
                    self.terminal.append(txt, tag)
            self.terminal.system("--- Assistente terminado ---")
            # Reset UI on completion
            self.after(0, self._on_assistant_exit)
        self._log_thread = threading.Thread(target=reader, daemon=True)
        self._log_thread.start()

    def _on_assistant_exit(self):
        """Called when the process ends to reset button and indicators."""
        self.btn_toggle.configure(text="▶  Iniciar NetEye", fg_color=ACCENT, hover_color="#3b7eef")
        self.lbl_status_run.configure(text="⬤  Parado", text_color=TEXT_3)
        self._status_dots["mic"].configure(fg_color=SURFACE_3)
        self._status_vals["mic"].configure(text="Inativo")
        self._status_dots["browser"].configure(fg_color=SURFACE_3)
        self._status_vals["browser"].configure(text="Fechado")
        self._process = None
