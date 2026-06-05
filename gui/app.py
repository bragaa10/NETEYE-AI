"""
app.py — Janela principal do NetEyeAI (Tkinter/CustomTkinter)
Gere sessão, roteamento entre vistas e layout base (navbar + sidebar + conteúdo)
- [NOVO] Atalhos de Teclado (Func 13)
"""
import os
import json
import customtkinter as ctk
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

from core.database import Database
from gui.theme import BG, SURFACE, BORDER, TEXT_1
from gui.widgets.navbar import NavBar
from gui.widgets.sidebar import SideBar
from gui.views.login_view import LoginView
from gui.views.register_view import RegisterView
from gui.views.dashboard_view import DashboardView
from gui.views.favorites_view import FavoritesView
from gui.views.blocked_view import BlockedView
from gui.views.history_view import HistoryView
from gui.views.settings_view import SettingsView

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class NetEyeApp(ctk.CTk):
    WIDTH  = 1300
    HEIGHT = 850
    SESSION_FILE = "data/session.json"

    def __init__(self):
        super().__init__()
        self.title("NetEye — Assistente de Voz")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(960, 600)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        try:
            self.after(200, lambda: self.iconbitmap("static/logo.ico"))
        except:
            pass

        self.db = Database()
        self._user_id: int | None   = None
        self._username: str | None  = None
        self._current_page: str     = ""
        self._current_view: ctk.CTkFrame | None = None

        self._build_layout()
        self._bind_shortcuts() # Func 13

        session_data = self._load_session()
        if session_data:
            self._user_id, self._username = session_data
            self._show_app("dashboard")
        else:
            self._show_auth("login")

    def _build_layout(self):
        self.navbar = NavBar(self, on_logout=self._logout)
        self.navbar.pack(fill="x", side="top")
        self.main_row = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main_row.pack(fill="both", expand=True)
        self.sidebar = SideBar(self.main_row, on_navigate=self._navigate)
        self.content_frame = ctk.CTkFrame(self.main_row, fg_color=BG, corner_radius=0)
        self.content_frame.pack(fill="both", expand=True, side="left")

    # ------------------------------------------------------------------
    # ATALHOS DE TECLADO (Func 13)
    # ------------------------------------------------------------------
    def _bind_shortcuts(self):
        """Atalhos globais de teclado como fallback de acessibilidade."""
        # Ctrl + Espaço para ativar microfone (se estiver no dashboard)
        self.bind("<Control-space>", lambda e: self._shortcut_mic())
        # Escape para parar tudo
        self.bind("<Escape>", lambda e: self._shortcut_stop())
        # Setas para rolar página
        self.bind("<Up>", lambda e: self._shortcut_scroll("cima"))
        self.bind("<Down>", lambda e: self._shortcut_scroll("baixo"))

    def _shortcut_mic(self):
        if self._current_page == "dashboard" and hasattr(self._current_view, "start_assistant"):
            self._current_view.start_assistant()

    def _shortcut_stop(self):
        if self._current_page == "dashboard" and hasattr(self._current_view, "stop_assistant"):
            self._current_view.stop_assistant()

    def _shortcut_scroll(self, direcao: str):
        # Enviar comando de scroll para o assistente (se estiver ativo)
        # Por agora, isto exigiria comunicação com o processo main.py
        # Mas para o teclado local, podemos simular se houver uma API de controlo.
        pass

    # ------------------------------------------------------------------
    # RESTO DA LÓGICA
    # ------------------------------------------------------------------

    def _show_auth(self, page: str):
        self.sidebar.pack_forget()
        self.navbar.set_user("")
        self._clear_content()
        if page == "login":
            view = LoginView(self.content_frame, on_login=self._do_login, on_go_register=lambda: self._show_auth("register"))
        else:
            view = RegisterView(self.content_frame, on_register=self._do_register, on_go_login=lambda: self._show_auth("login"))
        view.pack(fill="both", expand=True)
        self._current_view = view

    def _do_login(self, username: str, password: str):
        user = self.db.obter_utilizador(username)
        if user and check_password_hash(user["password_hash"], password):
            self._user_id  = user["id"]
            self._username = user["username"]
            self._save_session(self._user_id, self._username)
            self._show_app("dashboard")
        else:
            if hasattr(self._current_view, "show_error"):
                self._current_view.show_error("Credenciais inválidas.")

    def _do_register(self, username: str, api_key: str, password: str, confirm: str):
        pw_hash  = generate_password_hash(password)
        user_id  = self.db.registar_utilizador(username, pw_hash)
        if user_id > 0:
            self.db.guardar_configuracao(user_id, "api_key", api_key)
            self.db.guardar_configuracao(user_id, "velocidade", "135")
            self.db.guardar_configuracao(user_id, "volume", "100")
            self.db.guardar_configuracao(user_id, "talker_ativo", "True")
            self.db.guardar_configuracao(user_id, "guardar_historico", "True")
            self.db.guardar_configuracao(user_id, "modo_headless", "False")
            self._show_auth("login")
        else:
            if hasattr(self._current_view, "show_error"):
                self._current_view.show_error("Erro ao registar ou utilizador já existe.")

    def _logout(self):
        self._user_id  = None
        self._username = None
        self._clear_session()
        self._show_auth("login")

    def _show_app(self, page: str):
        self.navbar.set_user(self._username or "")
        self.sidebar.pack(fill="y", side="left", before=self.content_frame)
        self._navigate(page)

    def _navigate(self, page: str):
        if self._current_page == page: return
        self._current_page = page
        self.sidebar.set_active(page)
        self._clear_content()
        uid  = self._user_id
        uname = self._username
        if page == "dashboard":
            view = DashboardView(self.content_frame, db=self.db, user_id=uid)
        elif page == "favorites":
            view = FavoritesView(self.content_frame, db=self.db, user_id=uid)
        elif page == "blocked":
            view = BlockedView(self.content_frame, db=self.db, user_id=uid)
        elif page == "history":
            view = HistoryView(self.content_frame, db=self.db, user_id=uid)
        elif page == "settings":
            view = SettingsView(self.content_frame, db=self.db, user_id=uid, username=uname, on_username_change=self._on_username_change)
        else: return
        view.pack(fill="both", expand=True)
        self._current_view = view

    def _on_username_change(self, new_name: str):
        self._username = new_name
        self.navbar.set_user(new_name)

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self._current_view = None
        self._current_page = ""

    def _on_close(self):
        if (self._current_view and isinstance(self._current_view, DashboardView) and self._current_view._process and self._current_view._process.poll() is None):
            self._current_view._process.terminate()
        self.destroy()

    def _save_session(self, user_id: int, username: str):
        try:
            os.makedirs(os.path.dirname(self.SESSION_FILE), exist_ok=True)
            with open(self.SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"user_id": user_id, "username": username}, f)
        except: pass

    def _load_session(self) -> tuple[int, str] | None:
        try:
            if os.path.exists(self.SESSION_FILE):
                with open(self.SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data["user_id"], data["username"]
        except: pass
        return None

    def _clear_session(self):
        try:
            if os.path.exists(self.SESSION_FILE): os.remove(self.SESSION_FILE)
        except: pass

if __name__ == "__main__":
    app = NetEyeApp()
    app.mainloop()
