"""
navbar.py — Barra de topo do NetEye
Equivalente ao <nav> do base.html
"""
import customtkinter as ctk
from gui.theme import BG, SURFACE, SURFACE_2, ACCENT, GREEN, TEXT_1, TEXT_2, TEXT_3, BORDER, FONT_BRAND, FONT_BODY, FONT_BODY_SM


class NavBar(ctk.CTkFrame):
    """
    Barra de topo fixa com:
      👁 NetEye | [username badge] | [Sair]
    """

    def __init__(self, master, on_logout=None, **kwargs):
        super().__init__(
            master,
            fg_color=BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            height=52,
            **kwargs
        )
        self.on_logout = on_logout
        self.pack_propagate(False)
        self._build()

    def _build(self):
        # ── Lado esquerdo: logo ──────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", padx=20, fill="y")

        eye_badge = ctk.CTkFrame(
            left,
            width=30, height=30,
            corner_radius=8,
            fg_color=ACCENT,
        )
        eye_badge.pack(side="left", pady=10)
        eye_badge.pack_propagate(False)
        ctk.CTkLabel(eye_badge, text="👁", font=("Segoe UI", 13), text_color=TEXT_1).place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            left, text=" NetEye",
            font=FONT_BRAND,
            text_color=TEXT_1
        ).pack(side="left", pady=10)

        # ── Lado direito: user + sair ────────────────────────────────────
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="right", padx=20, fill="y")

        self.user_badge = ctk.CTkLabel(
            right, text="",
            font=("Consolas", 9),
            text_color=TEXT_2,
            fg_color=SURFACE_2,
            corner_radius=6,
            padx=10, pady=4
        )
        self.user_badge.pack(side="left", pady=10, padx=(0, 10))

        self.btn_logout = ctk.CTkButton(
            right, text="Sair",
            width=60, height=28,
            font=("Segoe UI", 9),
            fg_color="#3d1515",
            hover_color="#5a1f1f",
            text_color="#f87171",
            corner_radius=6,
            command=self._do_logout
        )
        self.btn_logout.pack(side="left", pady=10)

    def set_user(self, username: str):
        """Atualiza o badge do utilizador."""
        if username:
            self.user_badge.configure(text=f"  {username}  ")
            self.user_badge.pack(side="left", pady=10, padx=(0, 10))
            self.btn_logout.pack(side="left", pady=10)
        else:
            self.user_badge.pack_forget()
            self.btn_logout.pack_forget()

    def _do_logout(self):
        if self.on_logout:
            self.on_logout()
