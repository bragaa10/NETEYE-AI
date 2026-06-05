"""
login_view.py — Ecrã de Login
Equivalente a login.html
"""
# pyrefly: ignore [missing-import]
import customtkinter as ctk
from gui.theme import (
    BG, SURFACE, SURFACE_2, ACCENT, RED, TEXT_1, TEXT_2, TEXT_3,
    BORDER, FONT_TITLE, FONT_BODY, FONT_BOLD, FONT_BODY_SM
)


class LoginView(ctk.CTkFrame):
    """
    Card centrado com campos Username / Password.
    Chama on_login(username, password) ao submeter.
    Chama on_go_register() ao clicar no link de registo.
    """

    def __init__(self, master, on_login=None, on_go_register=None, **kwargs):
        super().__init__(master, fg_color=BG, corner_radius=0, **kwargs)
        self.on_login = on_login
        self.on_go_register = on_go_register
        self._build()

    def _build(self):
        # Centra o card verticalmente
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)

        card = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            corner_radius=16,
            border_width=1,
            border_color=BORDER,
            width=400,
        )
        card.grid(row=1, column=1, padx=20, pady=40, sticky="nsew")
        card.grid_propagate(False)
        card.configure(height=520)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=36, pady=32)

        # Título
        ctk.CTkLabel(
            inner, text="👁  NetEye",
            font=FONT_TITLE,
            text_color=TEXT_1
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            inner, text="Assistente de Voz Inteligente",
            font=FONT_BODY_SM,
            text_color=TEXT_3
        ).pack(pady=(0, 24))

        # Campo username
        ctk.CTkLabel(inner, text="Nome de Utilizador", font=FONT_BODY, text_color=TEXT_2, anchor="w").pack(fill="x")
        self.entry_user = ctk.CTkEntry(
            inner, placeholder_text="Ex: Herik",
            fg_color=SURFACE_2, border_color=BORDER,
            text_color=TEXT_1, placeholder_text_color=TEXT_3,
            height=38, corner_radius=8
        )
        self.entry_user.pack(fill="x", pady=(4, 14))
        self.entry_user.bind("<Return>", lambda e: self.entry_pass.focus())

        # Campo password
        ctk.CTkLabel(inner, text="Senha", font=FONT_BODY, text_color=TEXT_2, anchor="w").pack(fill="x")
        self.entry_pass = ctk.CTkEntry(
            inner, placeholder_text="Insira a sua senha",
            fg_color=SURFACE_2, border_color=BORDER,
            text_color=TEXT_1, placeholder_text_color=TEXT_3,
            show="●", height=38, corner_radius=8
        )
        self.entry_pass.pack(fill="x", pady=(4, 6))
        self.entry_pass.bind("<Return>", lambda e: self._submit())

        # Label de erro
        self.lbl_error = ctk.CTkLabel(
            inner, text="", font=FONT_BODY_SM,
            text_color=RED, wraplength=320
        )
        self.lbl_error.pack(pady=(4, 8))

        # Botão Entrar
        ctk.CTkButton(
            inner, text="Entrar",
            height=40, corner_radius=8,
            font=FONT_BOLD,
            fg_color=ACCENT,
            hover_color="#3b7eef",
            command=self._submit
        ).pack(fill="x")

        # Link Registo
        link_frame = ctk.CTkFrame(inner, fg_color="transparent")
        link_frame.pack(pady=(18, 0))
        ctk.CTkLabel(
            link_frame, text="Ainda não tem conta? ",
            font=FONT_BODY_SM, text_color=TEXT_3
        ).pack(side="left")
        btn_reg = ctk.CTkButton(
            link_frame, text="Registe-se aqui",
            font=FONT_BODY_SM, fg_color="transparent",
            text_color=ACCENT, hover_color=SURFACE,
            width=0, height=0,
            command=self._go_register
        )
        btn_reg.pack(side="left")

        self.entry_user.focus()

    def show_error(self, msg: str):
        self.lbl_error.configure(text=msg)

    def clear_error(self):
        self.lbl_error.configure(text="")

    def clear_fields(self):
        self.entry_user.delete(0, "end")
        self.entry_pass.delete(0, "end")
        self.clear_error()

    def _submit(self):
        u = self.entry_user.get().strip()
        p = self.entry_pass.get()
        if not u or not p:
            self.show_error("Preencha todos os campos.")
            return
        self.clear_error()
        if self.on_login:
            self.on_login(u, p)

    def _go_register(self):
        self.clear_fields()
        if self.on_go_register:
            self.on_go_register()
