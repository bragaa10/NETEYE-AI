"""
settings_view.py — Ecrã de Configurações
Equivalente a settings.html
- [NOVO] Exportação/Importação de Dados (Func 14)
- [FIX] Correção de métodos legado de base de dados
"""
import json
import customtkinter as ctk
from tkinter import filedialog, messagebox
from gui.theme import (
    BG, SURFACE, SURFACE_2, SURFACE_3, ACCENT, ACCENT_HOV, GREEN,
    RED, TEXT_1, TEXT_2, TEXT_3, BORDER,
    FONT_H2, FONT_H3, FONT_BODY, FONT_BOLD, FONT_BODY_SM
)

class SettingsView(ctk.CTkFrame):
    def __init__(self, master, db, user_id: int, username: str, on_username_change=None, **kwargs):
        super().__init__(master, fg_color=BG, corner_radius=0, **kwargs)
        self.db = db
        self.user_id = user_id
        self.username = username
        self.on_username_change = on_username_change
        self._voices: list[dict] = []
        self._build()
        self._load_configs()
        self._load_voices()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=BG, scrollbar_button_color=BORDER)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 0))
        ctk.CTkLabel(header, text="Configurações", font=FONT_H2, text_color=TEXT_1).pack(anchor="w")
        ctk.CTkLabel(header, text="Personalize a voz e o comportamento do assistente", font=FONT_BODY_SM, text_color=TEXT_3).pack(anchor="w")

        row1 = ctk.CTkFrame(scroll, fg_color="transparent")
        row1.pack(fill="x", padx=24, pady=(20, 0))
        row1.columnconfigure(0, weight=1)
        row1.columnconfigure(1, weight=1)

        self._build_voice_card(row1)
        self._build_behavior_card(row1)
        self._build_account_card(scroll)
        self._build_backup_card(scroll) # Func 14

        footer = ctk.CTkFrame(scroll, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(16, 24))
        self.lbl_success = ctk.CTkLabel(footer, text="", font=FONT_BODY_SM, text_color=GREEN)
        self.lbl_success.pack(side="left")
        ctk.CTkButton(footer, text="Guardar Alterações", height=40, width=180, corner_radius=8, font=FONT_BOLD, fg_color=ACCENT, hover_color="#3b7eef", command=self._save).pack(side="right")

    def _build_voice_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        ctk.CTkLabel(inner, text="🎙️  Voz e Idioma", font=FONT_H3, text_color=TEXT_1).pack(anchor="w", pady=(0, 12))
        ctk.CTkLabel(inner, text="Seletor de Voz (SAPI5)", font=FONT_BODY_SM, text_color=TEXT_2, anchor="w").pack(fill="x")
        self.cmb_voice = ctk.CTkComboBox(inner, values=["A carregar vozes..."], fg_color=SURFACE_2, border_color=BORDER, button_color=SURFACE_3, dropdown_fg_color=SURFACE_2, text_color=TEXT_1, corner_radius=8, height=36, state="readonly")
        self.cmb_voice.pack(fill="x", pady=(4, 16))
        
        ctk.CTkLabel(inner, text="Velocidade de Fala", font=FONT_BODY_SM, text_color=TEXT_2, anchor="w").pack(fill="x")
        vel_row = ctk.CTkFrame(inner, fg_color="transparent")
        vel_row.pack(fill="x", pady=(4, 12))
        self.slider_vel = ctk.CTkSlider(vel_row, from_=80, to=250, progress_color=ACCENT, button_color=ACCENT_HOV, fg_color=BORDER, command=self._update_vel_label)
        self.slider_vel.pack(side="left", fill="x", expand=True)
        self.lbl_vel = ctk.CTkLabel(vel_row, text="135", width=40, font=FONT_BODY_SM, text_color=TEXT_1)
        self.lbl_vel.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(inner, text="Volume", font=FONT_BODY_SM, text_color=TEXT_2, anchor="w").pack(fill="x")
        vol_row = ctk.CTkFrame(inner, fg_color="transparent")
        vol_row.pack(fill="x", pady=(4, 12))
        self.slider_vol = ctk.CTkSlider(vol_row, from_=0, to=100, progress_color=ACCENT, button_color=ACCENT_HOV, fg_color=BORDER, command=self._update_vol_label)
        self.slider_vol.pack(side="left", fill="x", expand=True)
        self.lbl_vol = ctk.CTkLabel(vol_row, text="100%", width=45, font=FONT_BODY_SM, text_color=TEXT_1)
        self.lbl_vol.pack(side="left", padx=(8, 0))

        ctk.CTkButton(inner, text="Testar Voz", height=34, width=120, corner_radius=8, font=FONT_BODY_SM, fg_color=SURFACE_2, hover_color=SURFACE_3, command=self._test_voice).pack(anchor="w", pady=(8, 0))

    def _build_behavior_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        ctk.CTkLabel(inner, text="🧠  Comportamento", font=FONT_H3, text_color=TEXT_1).pack(anchor="w", pady=(0, 16))
        self._switches: dict[str, ctk.CTkSwitch] = {}
        toggles = [
            ("talker_ativo",         "Talker Ativo (diz avisos enquanto processa)"),
            ("interromper_ao_falar", "Interromper voz ao falar"),
            ("guardar_historico",    "Guardar Histórico de navegação"),
            ("modo_headless",        "Modo Headless (Browser invisível)"),
        ]
        for key, label in toggles:
            sw = ctk.CTkSwitch(inner, text=label, font=FONT_BODY_SM, text_color=TEXT_2, progress_color=ACCENT, button_color=TEXT_1, onvalue="True", offvalue="False")
            sw.pack(anchor="w", pady=8)
            self._switches[key] = sw

    def _build_account_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=24, pady=(16, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(inner, text="👤  Conta", font=FONT_H3, text_color=TEXT_1).pack(anchor="w", pady=(0, 12))
        
        ctk.CTkLabel(inner, text="Nome de Utilizador", font=FONT_BODY_SM, text_color=TEXT_2, anchor="w").pack(fill="x")
        self.entry_username = ctk.CTkEntry(inner, fg_color=SURFACE_2, border_color=BORDER, text_color=TEXT_1, height=36, corner_radius=8)
        self.entry_username.pack(fill="x", pady=(4, 0))

    def _build_backup_card(self, parent):
        """Card para Exportar/Importar dados (Func 14)."""
        card = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=24, pady=(16, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(inner, text="💾  Backup e Dados", font=FONT_H3, text_color=TEXT_1).pack(anchor="w", pady=(0, 12))
        ctk.CTkLabel(inner, text="Exporte ou importe os seus favoritos, atalhos e sites bloqueados.", font=FONT_BODY_SM, text_color=TEXT_3).pack(anchor="w", pady=(0, 16))
        
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="📤 Exportar JSON", height=36, width=150, corner_radius=8, font=FONT_BOLD, fg_color=SURFACE_2, hover_color=SURFACE_3, command=self._export_data).pack(side="left", padx=(0, 12))
        ctk.CTkButton(btn_row, text="📥 Importar JSON", height=36, width=150, corner_radius=8, font=FONT_BOLD, fg_color=SURFACE_2, hover_color=SURFACE_3, command=self._import_data).pack(side="left")

    def _load_configs(self):
        configs = self.db.obter_todas_configuracoes(self.user_id)
        vel = int(configs.get("velocidade", 135))
        vol = int(configs.get("volume", 100))
        self.slider_vel.set(vel); self.slider_vol.set(vol)
        self.lbl_vel.configure(text=str(vel)); self.lbl_vol.configure(text=f"{vol}%")
        for key, sw in self._switches.items():
            if configs.get(key, "False") == "True": sw.select()
            else: sw.deselect()
        self.entry_username.delete(0, "end"); self.entry_username.insert(0, self.username)
        self._current_voice_id = configs.get("voz_local", "")

    def _load_voices(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
            self._voices = [{"id": v.id, "name": v.name} for v in voices]
            engine.stop()
        except Exception: self._voices = []
        if self._voices:
            names = [v["name"] for v in self._voices]
            self.cmb_voice.configure(values=names)
            for i, v in enumerate(self._voices):
                if v["id"] == self._current_voice_id: self.cmb_voice.set(names[i]); break
            else: self.cmb_voice.set(names[0])
        else: self.cmb_voice.configure(values=["Nenhuma voz disponível"]); self.cmb_voice.set("Nenhuma voz disponível")

    def _update_vel_label(self, val): self.lbl_vel.configure(text=str(int(val)))
    def _update_vol_label(self, val): self.lbl_vol.configure(text=f"{int(val)}%")

    def _test_voice(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", int(self.slider_vel.get()))
            engine.setProperty("volume", int(self.slider_vol.get()) / 100)
            sel_name = self.cmb_voice.get()
            for v in self._voices:
                if v["name"] == sel_name: engine.setProperty("voice", v["id"]); break
            engine.say("Teste de voz do NetEye bem sucedido.")
            engine.runAndWait()
        except Exception: pass

    def _export_data(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], title="Exportar Dados NetEye")
        if not path: return
        try:
            dados = self.db.exportar_dados(self.user_id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Sucesso", "Dados exportados com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao exportar: {e}")

    def _import_data(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], title="Importar Dados NetEye")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                dados = json.load(f)
            # Favoritos
            for fav in dados.get("favoritos", []):
                self.db.adicionar_favorito(self.user_id, fav["nome"], fav["url"])
            # Bloqueios
            for b in dados.get("bloqueios", []):
                self.db.adicionar_bloqueio(self.user_id, b["url"])
            # Atalhos
            for a in dados.get("atalhos", []):
                self.db.adicionar_atalho(self.user_id, a["frase"], a["acao"])
            messagebox.showinfo("Sucesso", "Dados importados com sucesso! Reinicie para ver todas as mudanças.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao importar: {e}")

    def _save(self):
        for key, sw in self._switches.items():
            self.db.guardar_configuracao(self.user_id, key, sw.get())
        self.db.guardar_configuracao(self.user_id, "velocidade", str(int(self.slider_vel.get())))
        self.db.guardar_configuracao(self.user_id, "volume", str(int(self.slider_vol.get())))
        sel_name = self.cmb_voice.get()
        for v in self._voices:
            if v["name"] == sel_name: self.db.guardar_configuracao(self.user_id, "voz_local", v["id"]); break

        new_user = self.entry_username.get().strip()
        if new_user and new_user != self.username:
            if self.db.atualizar_username(self.user_id, new_user): # Corrigido Bug Legado
                self.username = new_user
                if self.on_username_change: self.on_username_change(new_user)
        self.lbl_success.configure(text="[OK]  Configurações guardadas com sucesso!")
        self.after(3000, lambda: self.lbl_success.configure(text=""))
