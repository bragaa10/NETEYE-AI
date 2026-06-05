"""
favorites_view.py — Ecrã de Favoritos
Equivalente a favorites.html
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from gui.theme import (
    BG, SURFACE, SURFACE_2, SURFACE_3, ACCENT, ACCENT_HOV, ACCENT_GLOW,
    RED, TEXT_1, TEXT_2, TEXT_3, BORDER,
    FONT_H2, FONT_H3, FONT_BODY, FONT_BOLD, FONT_BODY_SM
)


class FavoritesView(ctk.CTkFrame):
    """Tabela de favoritos + botão adicionar + eliminar."""

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
        ctk.CTkLabel(left, text="Favoritos", font=FONT_H2, text_color=TEXT_1).pack(anchor="w")
        ctk.CTkLabel(left, text="Acesso rápido aos seus sites preferidos", font=FONT_BODY_SM, text_color=TEXT_3).pack(anchor="w")

        ctk.CTkButton(
            header, text="+ Novo Favorito",
            height=38, corner_radius=8,
            font=FONT_BOLD, fg_color=ACCENT, hover_color="#3b7eef",
            command=self._open_add_dialog
        ).pack(side="right")

        # ── Card tabela ──────────────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=24, pady=(18, 24))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Fav.Treeview",
            background=SURFACE, foreground=TEXT_1,
            fieldbackground=SURFACE, borderwidth=0,
            rowheight=30, font=("Segoe UI", 9)
        )
        style.configure("Fav.Treeview.Heading",
            background=SURFACE_2, foreground=TEXT_2,
            font=("Segoe UI", 9, "bold"), relief="flat"
        )
        style.map("Fav.Treeview", background=[("selected", ACCENT_GLOW)], foreground=[("selected", ACCENT_HOV)])

        tree_frame = tk.Frame(card, bg=SURFACE)
        tree_frame.pack(fill="both", expand=True, padx=14, pady=14)

        self.tree = ttk.Treeview(
            tree_frame, style="Fav.Treeview",
            columns=("nome", "url"),
            show="headings"
        )
        self.tree.heading("nome", text="Nome")
        self.tree.heading("url",  text="URL")
        self.tree.column("nome", width=200, stretch=False)
        self.tree.column("url",  width=400, stretch=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        # Botões de ação
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkButton(
            btn_row, text="📋 Copiar URL",
            height=32, width=130, corner_radius=8,
            font=FONT_BODY_SM, fg_color=SURFACE_2, hover_color=SURFACE_3,
            command=self._copy_url
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="🗑 Eliminar",
            height=32, width=110, corner_radius=8,
            font=FONT_BODY_SM, fg_color="#3d1515", hover_color="#5a1f1f",
            text_color=RED,
            command=self._delete_selected
        ).pack(side="left")

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        favs = self.db.listar_favoritos(self.user_id)
        if favs:
            for f in favs:
                self.tree.insert("", "end", iid=str(f["id"]), values=(f["nome"], f["url"]))
        else:
            self.tree.insert("", "end", values=("—", "Ainda não adicionou favoritos."))

    def _copy_url(self):
        sel = self.tree.selection()
        if not sel:
            return
        url = self.tree.item(sel[0])["values"][1]
        self.clipboard_clear()
        self.clipboard_append(url)

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        fav_id = int(sel[0])
        if messagebox.askyesno("Eliminar", "Tem a certeza que quer eliminar este favorito?"):
            self.db.remover_favorito_por_id(self.user_id, fav_id)
            self.refresh()

    def _open_add_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Adicionar Favorito")
        dialog.geometry("420x280")
        dialog.configure(fg_color=SURFACE)
        dialog.grab_set()
        dialog.resizable(False, False)

        inner = ctk.CTkFrame(dialog, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=28, pady=24)

        ctk.CTkLabel(inner, text="Adicionar Favorito", font=FONT_H3, text_color=TEXT_1).pack(anchor="w", pady=(0, 16))

        ctk.CTkLabel(inner, text="Nome do Site", font=FONT_BODY_SM, text_color=TEXT_2, anchor="w").pack(fill="x")
        entry_name = ctk.CTkEntry(inner, placeholder_text="Ex: Google",
            fg_color=SURFACE_2, border_color=BORDER, text_color=TEXT_1,
            placeholder_text_color=TEXT_3, height=36, corner_radius=8)
        entry_name.pack(fill="x", pady=(4, 12))

        ctk.CTkLabel(inner, text="Endereço (URL)", font=FONT_BODY_SM, text_color=TEXT_2, anchor="w").pack(fill="x")
        entry_url = ctk.CTkEntry(inner, placeholder_text="https://...",
            fg_color=SURFACE_2, border_color=BORDER, text_color=TEXT_1,
            placeholder_text_color=TEXT_3, height=36, corner_radius=8)
        entry_url.pack(fill="x", pady=(4, 16))

        lbl_err = ctk.CTkLabel(inner, text="", font=FONT_BODY_SM, text_color=RED)
        lbl_err.pack(anchor="w")

        def save():
            n = entry_name.get().strip()
            u = entry_url.get().strip()
            if not n or not u:
                lbl_err.configure(text="Preencha todos os campos.")
                return
            self.db.adicionar_favorito(self.user_id, n, u)
            self.refresh()
            dialog.destroy()

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(btn_row, text="Cancelar", fg_color=SURFACE_2, hover_color=SURFACE_3,
            width=100, height=36, corner_radius=8, command=dialog.destroy).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_row, text="Guardar", fg_color=ACCENT, hover_color="#3b7eef",
            width=100, height=36, corner_radius=8, command=save).pack(side="left")

        entry_name.focus()
