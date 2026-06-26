"""
register_view.py — Ecrã de Registo
Equivalente a register.html
"""
import os
import customtkinter as ctk
from PIL import Image
from gui.theme import (
    BG, SURFACE, SURFACE_2, ACCENT, ACCENT_HOV, RED, TEXT_1, TEXT_2, TEXT_3,
    BORDER, FONT_TITLE, FONT_BODY, FONT_BOLD, FONT_BODY_SM, RADIUS_MD, RADIUS_SM
)


class RegisterView(ctk.CTkFrame):
    """
    Formulário de registo com 3 campos:
    Username, Password, Confirmar Password.
    A chave API é partilhada e configurada no ficheiro .env.
    Chama on_register(username, password, confirm) ao submeter.
    Chama on_go_login() ao clicar no link de login.
    """

    def __init__(self, master, on_register=None, on_go_login=None, **kwargs):
        super().__init__(master, fg_color=BG, corner_radius=0, **kwargs)
        self.on_register = on_register
        self.on_go_login = on_go_login
        
        # Carregar Logo
        try:
            logo_path = os.path.join("static", "logo.png")
            if os.path.exists(logo_path):
                self.logo_img = ctk.CTkImage(
                    light_image=Image.open(logo_path),
                    dark_image=Image.open(logo_path),
                    size=(70, 70)
                )
            else:
                self.logo_img = None
        except Exception:
            self.logo_img = None
            
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)

        card = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            corner_radius=RADIUS_MD,
            border_width=1,
            border_color=BORDER,
        )
        card.grid(row=1, column=1, padx=20, pady=30, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=40, pady=30)

        # Logo
        if self.logo_img:
            ctk.CTkLabel(inner, image=self.logo_img, text="").pack(pady=(0, 8))

        ctk.CTkLabel(inner, text="Registar NetEye", font=FONT_TITLE, text_color=TEXT_1).pack(pady=(0, 2))
        ctk.CTkLabel(inner, text="Crie a sua conta para começar", font=FONT_BODY_SM, text_color=TEXT_3).pack(pady=(0, 20))

        def field(label, placeholder, show=None):
            ctk.CTkLabel(inner, text=label, font=FONT_BODY, text_color=TEXT_2, anchor="w").pack(fill="x")
            e = ctk.CTkEntry(
                inner, placeholder_text=placeholder,
                fg_color=SURFACE_2, border_color=BORDER,
                text_color=TEXT_1, placeholder_text_color=TEXT_3,
                show=show or "", height=42, corner_radius=RADIUS_SM, width=340
            )
            e.pack(fill="x", pady=(4, 12))
            return e

        self.entry_user    = field("Nome de Utilizador", "Como quer ser chamado?")
        self.entry_pass    = field("Senha", "Mínimo 6 caracteres", show="●")
        self.entry_confirm = field("Confirmar Senha", "Repita a senha", show="●")

        self.entry_user.bind("<Return>", lambda e: self.entry_pass.focus())
        self.entry_pass.bind("<Return>", lambda e: self.entry_confirm.focus())
        self.entry_confirm.bind("<Return>", lambda e: self._submit())

        # Erro
        self.lbl_error = ctk.CTkLabel(inner, text="", font=FONT_BODY_SM, text_color=RED, wraplength=340)
        self.lbl_error.pack(pady=(0, 6))

        ctk.CTkButton(
            inner, text="Criar Conta",
            height=44, corner_radius=RADIUS_SM,
            font=FONT_BOLD,
            fg_color=ACCENT, hover_color=ACCENT_HOV,
            width=340,
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

        self.entry_user.focus()

    def show_error(self, msg: str):
        self.lbl_error.configure(text=msg)

    def clear_fields(self):
        for e in [self.entry_user, self.entry_pass, self.entry_confirm]:
            e.delete(0, "end")
        self.lbl_error.configure(text="")

    def _submit(self):
        u = self.entry_user.get().strip()
        p = self.entry_pass.get()
        c = self.entry_confirm.get()

        if not u:
            self.show_error("Preencha o nome de utilizador.")
            return
        if len(p) < 6:
            self.show_error("A senha deve ter pelo menos 6 caracteres.")
            return
        if p != c:
            self.show_error("As senhas não coincidem.")
            return

        self.lbl_error.configure(text="")
        if self.on_register:
            self.on_register(u, p, c)

    def _go_login(self):
        self.clear_fields()
        if self.on_go_login:
            self.on_go_login()
