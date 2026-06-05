"""
sidebar.py — Barra lateral de navegação
Equivalente à <ul class="nav nav-pills"> do base.html
"""
import customtkinter as ctk
from gui.theme import SURFACE, SURFACE_2, SURFACE_3, ACCENT, ACCENT_GLOW, ACCENT_HOV, TEXT_1, TEXT_2, BORDER, FONT_BODY

NAV_ITEMS = [
    ("dashboard",  "📊", "Dashboard"),
    ("favorites",  "⭐", "Favoritos"),
    ("blocked",    "🚫", "Bloqueados"),
    ("history",    "📜", "Histórico"),
    ("settings",   "⚙️", "Configurações"),
]


class SideBar(ctk.CTkFrame):
    """
    Sidebar vertical com botões de navegação.
    Chama on_navigate(page_name) ao clicar.
    """

    def __init__(self, master, on_navigate=None, **kwargs):
        super().__init__(
            master,
            fg_color=SURFACE,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
            width=200,
            **kwargs
        )
        self.on_navigate = on_navigate
        self._active = None
        self._buttons: dict[str, ctk.CTkButton] = {}
        self.pack_propagate(False)
        self._build()

    def _build(self):
        ctk.CTkFrame(self, height=1, fg_color=BORDER).pack(fill="x")

        for key, icon, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                self,
                text=f"  {icon}  {label}",
                anchor="w",
                font=("Segoe UI", 10),
                fg_color="transparent",
                hover_color=SURFACE_2,
                text_color=TEXT_2,
                corner_radius=8,
                height=40,
                command=lambda k=key: self._click(k)
            )
            btn.pack(fill="x", padx=10, pady=3, ipady=2)
            self._buttons[key] = btn

    def set_active(self, page: str):
        """Destaca o item ativo."""
        if self._active == page:
            return
        # Desativar anterior
        if self._active and self._active in self._buttons:
            self._buttons[self._active].configure(
                fg_color="transparent",
                text_color=TEXT_2
            )
        # Ativar novo
        self._active = page
        if page in self._buttons:
            self._buttons[page].configure(
                fg_color=ACCENT_GLOW,
                text_color=ACCENT_HOV
            )

    def _click(self, key: str):
        self.set_active(key)
        if self.on_navigate:
            self.on_navigate(key)
