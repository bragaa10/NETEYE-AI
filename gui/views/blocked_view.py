"""
blocked_view.py — Ecrã de Sites Bloqueados
Equivalente a blocked.html
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from gui.theme import (
    BG, SURFACE, SURFACE_2, SURFACE_3, ACCENT, ACCENT_HOV, ACCENT_GLOW,
    RED, TEXT_1, TEXT_2, TEXT_3, BORDER,
    FONT_H2, FONT_H3, FONT_BODY, FONT_BOLD, FONT_BODY_SM
)


class BlockedView(ctk.CTkFrame):
    """Lista de domínios bloqueados com formulário inline de adição."""

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
        ctk.CTkLabel(left, text="Sites Bloqueados", font=FONT_H2, text_color=TEXT_1).pack(anchor="w")
        ctk.CTkLabel(left, text="Controle os domínios que o NetEye não deve aceder", font=FONT_BODY_SM, text_color=TEXT_3).pack(anchor="w")

        # ── Card Adicionar ───────────────────────────────────────────────
        add_card = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
        add_card.pack(fill="x", padx=24, pady=(18, 0))

        add_inner = ctk.CTkFrame(add_card, fg_color="transparent")
        add_inner.pack(fill="x", padx=18, pady=14)
        add_inner.columnconfigure(0, weight=1)

        ctk.CTkLabel(add_inner, text="Novo Domínio", font=FONT_BODY_SM, text_color=TEXT_2, anchor="w").grid(row=0, column=0, sticky="w")
        self.entry_domain = ctk.CTkEntry(
            add_inner, placeholder_text="Ex: facebook.com",
            fg_color=SURFACE_2, border_color=BORDER,
            text_color=TEXT_1, placeholder_text_color=TEXT_3,
            height=38, corner_radius=8
        )
        self.entry_domain.grid(row=1, column=0, sticky="ew", pady=(4, 0), padx=(0, 12))
        self.entry_domain.bind("<Return>", lambda e: self._add_domain())

        ctk.CTkButton(
            add_inner, text="Bloquear",
            height=38, width=120, corner_radius=8,
            font=FONT_BOLD, fg_color="#8b1a1a", hover_color="#a52020",
            text_color=TEXT_1,
            command=self._add_domain
        ).grid(row=1, column=1, sticky="e", pady=(4, 0))

        self.lbl_err = ctk.CTkLabel(add_inner, text="", font=FONT_BODY_SM, text_color=RED)
        self.lbl_err.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # ── Card Tabela ──────────────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=24, pady=(12, 24))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Blk.Treeview",
            background=SURFACE, foreground=TEXT_1,
            fieldbackground=SURFACE, borderwidth=0,
            rowheight=30, font=("Segoe UI", 9)
        )
        style.configure("Blk.Treeview.Heading",
            background=SURFACE_2, foreground=TEXT_2,
            font=("Segoe UI", 9, "bold"), relief="flat"
        )
        style.map("Blk.Treeview", background=[("selected", ACCENT_GLOW)], foreground=[("selected", ACCENT_HOV)])

        tree_frame = tk.Frame(card, bg=SURFACE)
        tree_frame.pack(fill="both", expand=True, padx=14, pady=14)

        self.tree = ttk.Treeview(
            tree_frame, style="Blk.Treeview",
            columns=("dominio",),
            show="headings"
        )
        self.tree.heading("dominio", text="Domínio")
        self.tree.column("dominio", stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkButton(
            btn_row, text="🔓 Desbloquear",
            height=32, width=140, corner_radius=8,
            font=FONT_BODY_SM, fg_color=SURFACE_2, hover_color=SURFACE_3,
            command=self._unblock_selected
        ).pack(side="left")

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        blocks = self.db.listar_bloqueios(self.user_id)
        if blocks:
            for b in blocks:
                self.tree.insert("", "end", iid=str(b["id"]), values=(b["url"],))
        else:
            self.tree.insert("", "end", values=("Nenhum site bloqueado.",))

    def _add_domain(self):
        domain = self.entry_domain.get().strip()
        if not domain:
            self.lbl_err.configure(text="Insira um domínio.")
            return
        self.lbl_err.configure(text="")
        self.db.adicionar_bloqueio(self.user_id, domain)
        self.entry_domain.delete(0, "end")
        self.refresh()

    def _unblock_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        blk_id = int(sel[0])
        if messagebox.askyesno("Desbloquear", "Tem a certeza que quer desbloquear este domínio?"):
            self.db.remover_bloqueio_por_id(self.user_id, blk_id)
            self.refresh()
