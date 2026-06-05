"""
theme.py — Paleta de cores e estilos do NetEyeAI
Espelho fiel do style.css existente
"""

# ─── Cores ──────────────────────────────────────────────────────────────────
BG          = "#05080f"
SURFACE     = "#0c1220"
SURFACE_2   = "#111d30"
SURFACE_3   = "#162038"
ACCENT      = "#4f8eff"
ACCENT_GLOW = "#1a2d55"
ACCENT_HOV  = "#7aaeff"
GREEN       = "#34d399"
GREEN_DIM   = "#1a3d2e"
RED         = "#f87171"
AMBER       = "#fbbf24"
BORDER      = "#14213d"
TEXT_1      = "#f0f4ff"
TEXT_2      = "#8fa3c8"
TEXT_3      = "#4d6490"

# ─── Fontes ──────────────────────────────────────────────────────────────────
FONT_BODY    = ("Segoe UI", 12)
FONT_BODY_SM = ("Segoe UI", 11)
FONT_BOLD    = ("Segoe UI", 12, "bold")
FONT_TITLE   = ("Segoe UI", 24, "bold")
FONT_H2      = ("Segoe UI", 18, "bold")
FONT_H3      = ("Segoe UI", 14, "bold")
FONT_MONO    = ("Consolas", 11)
FONT_BRAND   = ("Segoe UI", 18, "bold")
FONT_STAT    = ("Segoe UI", 32, "bold")

# ─── Raios / espaçamentos ─────────────────────────────────────────────────────
RADIUS_SM = 10
RADIUS_MD = 14
RADIUS_LG = 18

PAD_SM = 10
PAD_MD = 20
PAD_LG = 30

# ─── Configuração CustomTkinter ───────────────────────────────────────────────
CTK_THEME = {
    "CTk": {
        "fg_color": [BG, BG],
    },
    "CTkFrame": {
        "fg_color": [SURFACE, SURFACE],
        "border_color": [BORDER, BORDER],
        "border_width": 1,
        "corner_radius": RADIUS_MD,
    },
    "CTkButton": {
        "fg_color": [ACCENT, ACCENT],
        "hover_color": [ACCENT_HOV, ACCENT_HOV],
        "text_color": [TEXT_1, TEXT_1],
        "corner_radius": RADIUS_SM,
        "border_width": 0,
        "height": 45,  # Increased height
    },
    "CTkEntry": {
        "fg_color": [SURFACE_2, SURFACE_2],
        "border_color": [BORDER, BORDER],
        "text_color": [TEXT_1, TEXT_1],
        "placeholder_text_color": [TEXT_3, TEXT_3],
        "corner_radius": RADIUS_SM,
        "height": 42,  # Increased height
    },
    "CTkLabel": {
        "text_color": [TEXT_1, TEXT_1],
    },
    "CTkTextbox": {
        "fg_color": [SURFACE_2, SURFACE_2],
        "border_color": [BORDER, BORDER],
        "text_color": [TEXT_2, TEXT_2],
        "corner_radius": RADIUS_SM,
    },
    "CTkScrollableFrame": {
        "fg_color": [SURFACE, SURFACE],
        "label_fg_color": [SURFACE, SURFACE],
    },
    "CTkSwitch": {
        "progress_color": [ACCENT, ACCENT],
        "button_color": [TEXT_1, TEXT_1],
        "button_hover_color": [TEXT_2, TEXT_2],
        "text_color": [TEXT_2, TEXT_2],
    },
    "CTkSlider": {
        "progress_color": [ACCENT, ACCENT],
        "button_color": [ACCENT_HOV, ACCENT_HOV],
        "fg_color": [BORDER, BORDER],
    },
    "CTkComboBox": {
        "fg_color": [SURFACE_2, SURFACE_2],
        "border_color": [BORDER, BORDER],
        "button_color": [SURFACE_3, SURFACE_3],
        "text_color": [TEXT_1, TEXT_1],
        "corner_radius": RADIUS_SM,
        "height": 42,
    },
    "CTkOptionMenu": {
        "fg_color": [SURFACE_2, SURFACE_2],
        "button_color": [SURFACE_3, SURFACE_3],
        "text_color": [TEXT_1, TEXT_1],
        "corner_radius": RADIUS_SM,
        "height": 42,
    },
}
