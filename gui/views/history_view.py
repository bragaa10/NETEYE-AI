"""
history_view.py — Ecrã de Histórico Completo
Equivalente a history.html
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from gui.theme import (
    BG, SURFACE, SURFACE_2, SURFACE_3, ACCENT, ACCENT_HOV, ACCENT_GLOW,
    RED, TEXT_1, TEXT_2, TEXT_3, BORDER,
    FONT_H2, FONT_BODY, FONT_BOLD, FONT_BODY_SM
)


class HistoryView(ctk.CTkFrame):
    """Histórico completo de navegação com botão 'Limpar Tudo'."""

    def __init__(self, master, db, user_id: int, **kwargs):
        super().__init__(master, fg_color=BG, corner_radius=0, **kwargs)
        self.db = db
        self.user_id = user_id
        self._build()
        self.refresh()

    def _build(self):
        # ── Cabeçalho ────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 0))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="Histórico Completo", font=FONT_H2, text_color=TEXT_1).pack(anchor="w")
        ctk.CTkLabel(
            left, text="Registo de todas as páginas visitadas pelo assistente",
            font=FONT_BODY_SM, text_color=TEXT_3
        ).pack(anchor="w")

        self.btn_clear = ctk.CTkButton(
            header, text="🗑  Limpar Tudo",
            height=38, corner_radius=8,
            font=FONT_BOLD,
            fg_color="#3d1515", hover_color="#5a1f1f",
            text_color=RED,
            command=self._clear_all
        )
        self.btn_clear.pack(side="right")

        # ── Card Tabela ──────────────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=24, pady=(18, 24))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Hist.Treeview",
            background=SURFACE, foreground=TEXT_1,
            fieldbackground=SURFACE, borderwidth=0,
            rowheight=30, font=("Segoe UI", 9)
        )
        style.configure("Hist.Treeview.Heading",
            background=SURFACE_2, foreground=TEXT_2,
            font=("Segoe UI", 9, "bold"), relief="flat"
        )
        style.map("Hist.Treeview",
            background=[("selected", ACCENT_GLOW)],
            foreground=[("selected", ACCENT_HOV)]
        )

        tree_frame = tk.Frame(card, bg=SURFACE)
        tree_frame.pack(fill="both", expand=True, padx=14, pady=14)

        self.tree = ttk.Treeview(
            tree_frame, style="Hist.Treeview",
            columns=("data", "titulo", "url"),
            show="headings"
        )
        self.tree.heading("data",   text="Data e Hora")
        self.tree.heading("titulo", text="Título da Página")
        self.tree.heading("url",    text="URL")
        self.tree.column("data",   width=140, stretch=False)
        self.tree.column("titulo", width=220, stretch=False)
        self.tree.column("url",    stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        hist = self.db.historico_completo(self.user_id)
        if hist:
            for item in hist:
                visit = item.get("data_visita", "") or ""
                if "T" in visit:
                    data = visit.split("T")[0] + " " + visit.split("T")[1][:8]
                elif len(visit) >= 19:
                    data = visit[:10] + " " + visit[11:19]
                else:
                    data = visit
                titulo = item.get("titulo") or "Sem Título"
                url = item.get("url", "")
                self.tree.insert("", "end", values=(data, titulo, url))
        else:
            self.tree.insert("", "end", values=("—", "Nenhum histórico registado.", ""))

    def _clear_all(self):
        if messagebox.askyesno("Limpar Histórico", "Tem a certeza que deseja limpar todo o histórico?"):
            self.db.limpar_historico(self.user_id)
            self.refresh()
