"""
register_view.py — Ecrã de Registo
Equivalente a register.html
"""
import customtkinter as ctk
from gui.theme import (
    BG, SURFACE, SURFACE_2, ACCENT, RED, TEXT_1, TEXT_2, TEXT_3,
    BORDER, FONT_TITLE, FONT_BODY, FONT_BOLD, FONT_BODY_SM
)


class RegisterView(ctk.CTkFrame):
    """
    Formulário de registo com 4 campos:
    Username, API Key, Password, Confirmar Password.
    Chama on_register(username, api_key, password, confirm) ao submeter.
    Chama on_go_login() ao clicar no link de login.
    """

    def __init__(self, master, on_register=None, on_go_login=None, **kwargs):
        super().__init__(master, fg_color=BG, corner_radius=0, **kwargs)
        self.on_register = on_register
        self.on_go_login = on_go_login
        self._build()

    def _build(self):
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
            width=420,
        )
        card.grid(row=1, column=1, padx=20, pady=30, sticky="nsew")
        card.grid_propagate(False)
        card.configure(height=680)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=36, pady=28)

        ctk.CTkLabel(inner, text="Registar NetEye", font=FONT_TITLE, text_color=TEXT_1).pack(pady=(0, 4))
        ctk.CTkLabel(inner, text="Crie a sua conta para começar", font=FONT_BODY_SM, text_color=TEXT_3).pack(pady=(0, 20))

        def field(label, placeholder, show=None):
            ctk.CTkLabel(inner, text=label, font=FONT_BODY, text_color=TEXT_2, anchor="w").pack(fill="x")
            e = ctk.CTkEntry(
                inner, placeholder_text=placeholder,
                fg_color=SURFACE_2, border_color=BORDER,
                text_color=TEXT_1, placeholder_text_color=TEXT_3,
                show=show or "", height=36, corner_radius=8
            )
            e.pack(fill="x", pady=(4, 12))
            return e

        self.entry_user    = field("Nome de Utilizador", "Como quer ser chamado?")
        self.entry_api     = field("Chave API Anthropic (Claude)", "sk-ant-...")
        self.entry_pass    = field("Senha", "Mínimo 6 caracteres", show="●")
        self.entry_confirm = field("Confirmar Senha", "Repita a senha", show="●")

        ctk.CTkLabel(
            inner, text="A chave deve começar por  sk-ant-",
            font=("Consolas", 8), text_color=TEXT_3
        ).pack(anchor="w", pady=(0, 8))

        # Erro
        self.lbl_error = ctk.CTkLabel(inner, text="", font=FONT_BODY_SM, text_color=RED, wraplength=340)
        self.lbl_error.pack(pady=(0, 6))

        ctk.CTkButton(
            inner, text="Criar Conta",
            height=40, corner_radius=8,
            font=FONT_BOLD,
            fg_color=ACCENT, hover_color="#3b7eef",
            command=self._submit
        ).pack(fill="x")

        # Link login
        lf = ctk.CTkFrame(inner, fg_color="transparent")
        lf.pack(pady=(16, 0))
        ctk.CTkLabel(lf, text="Já tem conta? ", font=FONT_BODY_SM, text_color=TEXT_3).pack(side="left")
        ctk.CTkButton(
            lf, text="Inicie sessão",
            font=FONT_BODY_SM, fg_color="transparent",
            text_color=ACCENT, hover_color=SURFACE,
            width=0, height=0, command=self._go_login
        ).pack(side="left")

    def show_error(self, msg: str):
        self.lbl_error.configure(text=msg)

    def clear_fields(self):
        for e in [self.entry_user, self.entry_api, self.entry_pass, self.entry_confirm]:
            e.delete(0, "end")
        self.lbl_error.configure(text="")

    def _submit(self):
        u  = self.entry_user.get().strip()
        ak = self.entry_api.get().strip()
        p  = self.entry_pass.get()
        c  = self.entry_confirm.get()

        if not u or not ak:
            self.show_error("Preencha todos os campos.")
            return
        if not ak.startswith("sk-ant-"):
            self.show_error("A chave API deve começar por 'sk-ant-'.")
            return
        if len(p) < 6:
            self.show_error("A senha deve ter pelo menos 6 caracteres.")
            return
        if p != c:
            self.show_error("As senhas não coincidem.")
            return

        self.lbl_error.configure(text="")
        if self.on_register:
            self.on_register(u, ak, p, c)

    def _go_login(self):
        self.clear_fields()
        if self.on_go_login:
            self.on_go_login()
