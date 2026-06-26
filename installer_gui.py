"""
installer_gui.py — Assistente de Instalação WEB para NetEyeAI
Versão Bootstrapper que descarrega a última versão do GitHub.
"""
import os
import sys
# Configurar codificação UTF-8 para consola para evitar erros com emojis no Windows (cp1252)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import shutil
import threading
import subprocess
import zipfile
import requests
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

def find_python_and_pythonw():
    """
    Tenta localizar de forma robusta os executáveis python.exe e pythonw.exe.
    Retorna um par (python_path, pythonw_path).
    """
    import sys
    import os
    import shutil

    # 1. Verificar se o sys.executable atual é um interpretador de python
    executable = sys.executable
    if executable and "python" in os.path.basename(executable).lower() and ("python.exe" in executable.lower() or "pythonw.exe" in executable.lower()):
        py = executable
        pyw = executable.lower().replace("python.exe", "pythonw.exe")
        if os.path.exists(pyw):
            return py, pyw
        return py, py

    # 2. Procurar no PATH do sistema usando shutil.which
    py = shutil.which("python")
    pyw = shutil.which("pythonw")
    if py and pyw:
        return py, pyw
    if py:
        pyw_infer = py.lower().replace("python.exe", "pythonw.exe")
        if os.path.exists(pyw_infer):
            return py, pyw_infer
        return py, py

    # 3. Procurar em diretórios padrão do Windows (Users\...\AppData\Local\Programs\Python ou Program Files)
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    system_drive = os.environ.get("SystemDrive", "C:")
    
    search_dirs = []
    if local_appdata:
        search_dirs.append(os.path.join(local_appdata, "Programs", "Python"))
    if program_files:
        search_dirs.append(os.path.join(program_files, "Python"))
    search_dirs.append(os.path.join(system_drive, "\\"))
    
    for base_dir in search_dirs:
        if not os.path.exists(base_dir):
            continue
        try:
            for item in os.listdir(base_dir):
                if item.lower().startswith("python"):
                    sub_path = os.path.join(base_dir, item)
                    if os.path.isdir(sub_path):
                        py_cand = os.path.join(sub_path, "python.exe")
                        pyw_cand = os.path.join(sub_path, "pythonw.exe")
                        if os.path.exists(py_cand):
                            if os.path.exists(pyw_cand):
                                return py_cand, pyw_cand
                            return py_cand, py_cand
        except Exception:
            pass

    # 4. Fallback absoluto
    return "python", "pythonw"

# Configuração do Repositório (Altera para o teu!)
REPO_OWNER = "bragaa10"
REPO_NAME = "NETEYE-AI"
ASSET_NAME = "NetEyeAI.zip"

# Cores Design System
BG        = "#0a0f1d"
SURFACE   = "#111827"
SURFACE_2 = "#1f2937"
ACCENT    = "#3b82f6"
TEXT_1    = "#ffffff"
TEXT_2    = "#ffffff"
TEXT_3    = "#ffffff"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class NetEyeInstaller(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("NetEyeAI — Setup")
        self.geometry("750x520")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        
        # Estado
        self.install_path = os.path.join(os.environ["LOCALAPPDATA"], "NetEyeAI")
        self.current_step = 1
        self.launch_after = tk.BooleanVar(value=True)
        self.create_shortcut = tk.BooleanVar(value=True)
        self.download_url = None
        
        # Carregar Logo e Ícone
        try:
            self.iconbitmap("static/logo.ico")
            self.logo_img = ctk.CTkImage(
                light_image=Image.open("static/logo.png"),
                dark_image=Image.open("static/logo.png"),
                size=(140, 140)
            )
        except Exception:
            self.logo_img = None

        self._build_ui()
        self._show_step(1)

    def _build_ui(self):
        self.side_panel = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=SURFACE_2)
        self.side_panel.pack(side="left", fill="y")
        if self.logo_img:
            ctk.CTkLabel(self.side_panel, image=self.logo_img, text="").pack(pady=(50, 20))
        ctk.CTkLabel(self.side_panel, text="NetEyeAI", font=("Segoe UI", 24, "bold"), text_color="#ffffff").pack()
        ctk.CTkLabel(self.side_panel, text="PAP 2025-26", font=("Segoe UI", 12), text_color=TEXT_3).pack(pady=5)
        self.status_dot = ctk.CTkLabel(self.side_panel, text="● Pronto", text_color="#10b981", font=("Segoe UI", 11))
        self.status_dot.pack(side="bottom", pady=20)

        self.container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.container.pack(side="right", fill="both", expand=True, padx=40, pady=30)
        self.content_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)
        self.nav_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.nav_frame.pack(side="bottom", fill="x", pady=(20, 0))
        self.btn_next = ctk.CTkButton(self.nav_frame, text="Seguinte >", command=self._next_step, fg_color=ACCENT, hover_color="#2563eb", width=120, height=35)
        self.btn_next.pack(side="right", padx=5)
        self.btn_prev = ctk.CTkButton(self.nav_frame, text="< Anterior", command=self._prev_step, fg_color=SURFACE_2, hover_color="#374151", width=100, height=35)
        self.btn_prev.pack(side="right", padx=5)

    def _show_step(self, step):
        for widget in self.content_frame.winfo_children(): widget.destroy()
        steps = {1: self._step_welcome, 2: self._step_info, 3: self._step_path, 4: self._step_summary, 5: self._step_install, 6: self._step_finish}
        steps[step]()

    # --- PAGES ---

    def _step_welcome(self):
        self.btn_prev.configure(state="disabled")
        ctk.CTkLabel(self.content_frame, text="Bem-vindo ao Setup", font=("Segoe UI", 28, "bold"), text_color=TEXT_1, anchor="w").pack(fill="x")
        desc = ("Este assistente irá descarregar e instalar o NetEyeAI no seu computador.\n\n"
                "A plataforma será instalada de forma segura e configurada para arrancar imediatamente.")
        ctk.CTkLabel(self.content_frame, text=desc, font=("Segoe UI", 14), text_color=TEXT_2, wraplength=420, justify="left").pack(pady=30, anchor="w")
        tips_frame = ctk.CTkFrame(self.content_frame, fg_color=SURFACE_2, corner_radius=10)
        tips_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(tips_frame, text="💡 O instalador irá buscar a versão mais recente do GitHub.", font=("Segoe UI", 12, "italic"), text_color=TEXT_3, padx=15, pady=10).pack()

    def _step_info(self):
        self.btn_prev.configure(state="normal")
        ctk.CTkLabel(self.content_frame, text="Requisitos da Web", font=("Segoe UI", 22, "bold"), text_color=TEXT_1, anchor="w").pack(fill="x")
        reqs = [
            ("🌐 Ligação", "Necessária para descarregar o pacote de ~400MB."),
            ("🎙️ Microfone", "Deve estar ligado para comandos de voz."),
            ("💾 Espaço", "Espaço livre necessário em C:\\ ou pasta escolhida.")
        ]
        for icon, txt in reqs:
            f = ctk.CTkFrame(self.content_frame, fg_color="transparent"); f.pack(fill="x", pady=8)
            ctk.CTkLabel(f, text=icon, font=("Segoe UI", 14, "bold"), text_color="#ffffff", width=100, anchor="w").pack(side="left")
            ctk.CTkLabel(f, text=txt, font=("Segoe UI", 13), text_color=TEXT_2).pack(side="left")

    def _step_path(self):
        ctk.CTkLabel(self.content_frame, text="Destino da Instalação", font=("Segoe UI", 22, "bold"), text_color=TEXT_1, anchor="w").pack(fill="x")
        self.path_entry = ctk.CTkEntry(self.content_frame, fg_color=SURFACE_2, border_color=ACCENT, height=40, text_color="#ffffff")
        self.path_entry.pack(fill="x", pady=10)
        self.path_entry.insert(0, self.install_path)
        ctk.CTkButton(self.content_frame, text="📁 Alterar Pasta", fg_color=SURFACE_2, command=self._browse_path).pack(anchor="e", pady=(0, 20))
        
        # Checkbox para atalho opcional
        ctk.CTkCheckBox(self.content_frame, text="Criar atalho no Ambiente de Trabalho (Área de Trabalho)", variable=self.create_shortcut, fg_color=ACCENT, text_color="#ffffff").pack(anchor="w", pady=10)

    def _step_summary(self):
        ctk.CTkLabel(self.content_frame, text="Resumo da Instalação", font=("Segoe UI", 22, "bold"), text_color=TEXT_1, anchor="w").pack(fill="x")
        atalho_str = "Sim" if self.create_shortcut.get() else "Não"
        summary = f"Tipo: Instalação Web (Auto-Download)\nDestino: {self.install_path}\nAtalho no Desktop: {atalho_str}"
        box = ctk.CTkFrame(self.content_frame, fg_color=SURFACE_2, corner_radius=10); box.pack(fill="both", expand=True, pady=20)
        ctk.CTkLabel(box, text=summary, font=("Segoe UI", 13), text_color=TEXT_2, justify="left", padx=20, pady=20).pack(anchor="nw")
        self.btn_next.configure(text="Instalar", fg_color="#10b981", hover_color="#059669")

    def _step_install(self):
        self.btn_next.configure(state="disabled"); self.btn_prev.configure(state="disabled")
        self.status_dot.configure(text="● A Descarregar", text_color="#ffffff")
        ctk.CTkLabel(self.content_frame, text="A Descarregar e Instalar", font=("Segoe UI", 22, "bold"), text_color=TEXT_1, anchor="w").pack(fill="x")
        self.progress_bar = ctk.CTkProgressBar(self.content_frame, height=12, fg_color=SURFACE_2, progress_color=ACCENT); self.progress_bar.pack(fill="x", pady=(40, 10)); self.progress_bar.set(0)
        self.pct_lbl = ctk.CTkLabel(self.content_frame, text="0%", font=("Segoe UI", 16, "bold"), text_color=TEXT_1); self.pct_lbl.pack()
        self.status_lbl = ctk.CTkLabel(self.content_frame, text="A contactar GitHub...", font=("Segoe UI", 12), text_color=TEXT_3); self.status_lbl.pack(pady=10)
        threading.Thread(target=self._run_web_installation, daemon=True).start()

    def _step_finish(self):
        self.status_dot.configure(text="● Concluído", text_color="#10b981")
        ctk.CTkLabel(self.content_frame, text="Pronto para usar!", font=("Segoe UI", 28, "bold"), text_color="#ffffff", anchor="w").pack(fill="x")
        ctk.CTkLabel(self.content_frame, text="O NetEyeAI foi instalado com sucesso.", font=("Segoe UI", 14), text_color=TEXT_2, anchor="w").pack(fill="x", pady=20)
        ctk.CTkCheckBox(self.content_frame, text="Abrir NetEyeAI agora", variable=self.launch_after, fg_color=ACCENT, text_color="#ffffff").pack(anchor="w", pady=20)
        self.btn_next.configure(text="Concluir", state="normal", command=self._finish_all, fg_color=ACCENT)
        self.btn_prev.pack_forget()

    # --- LOGIC ---

    def _run_web_installation(self):
        try:
            # 1. Obter Download URL do GitHub (tentar release ou fallback para main branch)
            self.download_url = None
            try:
                api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
                res = requests.get(api_url, timeout=10)
                if res.status_code == 200:
                    for asset in res.json().get("assets", []):
                        if asset["name"] == ASSET_NAME:
                            self.download_url = asset["browser_download_url"]
                            break
            except Exception:
                pass

            # Se não houver releases, descarrega o zip da branch main diretamente
            if not self.download_url:
                self.after(0, lambda: self.status_lbl.configure(text="A usar a branch main do repositório..."))
                self.download_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/main.zip"

            # 2. Download
            import tempfile
            zip_path = os.path.join(tempfile.gettempdir(), "temp_install.zip")
            with requests.get(self.download_url, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                done = 0
                with open(zip_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk); done += len(chunk)
                        # Se o tamanho total for desconhecido (como no zip do GitHub), envia progresso fictício
                        pct = int((done / total) * 100) if total > 0 else 50
                        self.after(0, lambda p=pct: self._update_progress(p, "A descarregar..."))
            
            # 3. Extração
            self.after(0, lambda: self.status_lbl.configure(text="A extrair ficheiros..."))
            target = os.path.abspath(self.install_path)
            if not target.lower().endswith("neteyeai"):
                target = os.path.join(target, "NetEyeAI")
            self.install_path = target
            
            # Função para remover atributo de somente leitura no Windows em caso de erro
            def remove_readonly(func, path, excinfo):
                import stat
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass
                    
            if os.path.exists(target) and target.lower().endswith("neteyeai"):
                shutil.rmtree(target, onerror=remove_readonly)
                
            os.makedirs(target, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Proteção contra Zip Slip
                for member in zip_ref.namelist():
                    member_path = os.path.realpath(os.path.join(target, member))
                    if not member_path.startswith(os.path.realpath(target)):
                        raise Exception("Path traversal detectado no ZIP!")
                zip_ref.extractall(target)
            try:
                os.remove(zip_path)
            except Exception:
                pass

            # Mover ficheiros se estiverem dentro de uma pasta aninhada (ex: NETEYE-AI-main)
            conteudo = os.listdir(target)
            if len(conteudo) == 1 and os.path.isdir(os.path.join(target, conteudo[0])):
                nested_dir = os.path.join(target, conteudo[0])
                for item in os.listdir(nested_dir):
                    try:
                        shutil.move(os.path.join(nested_dir, item), target)
                    except Exception:
                        pass
                try:
                    shutil.rmtree(nested_dir, onerror=remove_readonly)
                except Exception:
                    pass

            # Criar o ficheiro .env com template de overrides (as credenciais reais vêm pré-empacotadas)
            env_content = (
                "# NetEye — Configurações Locais\n"
                "# As credenciais de produção padrão já vêm embutidas no programa.\n"
                "# Use as variáveis abaixo apenas se desejar substituir a BD ou chave de encriptação padrão:\n"
                "# SUPABASE_URL=https://...\n"
                "# SUPABASE_KEY=...\n"
                "# NETEYE_ENCRYPTION_KEY=...\n"
            )
            with open(os.path.join(target, ".env"), "w", encoding="utf-8") as env_file:
                env_file.write(env_content)

            # 4. Instalar Requisitos (requirements.txt)
            self.after(0, lambda: self.status_lbl.configure(text="A instalar dependências (requirements.txt)..."))
            req_file = os.path.join(target, "requirements.txt")
            real_python, pyw_exe = find_python_and_pythonw()
            if os.path.exists(req_file):
                # Executar pip install usando o executável python real
                res_pip = subprocess.run([real_python, "-m", "pip", "install", "-r", "requirements.txt"], cwd=target, text=True, capture_output=True)
                if res_pip.returncode != 0:
                    raise Exception(f"Falha ao instalar dependências: {res_pip.stderr}")

            # Instalar Chromium via Playwright
            self.after(0, lambda: self.status_lbl.configure(text="A instalar browser Chromium (Playwright)..."))
            res_pw = subprocess.run([real_python, "-m", "playwright", "install", "chromium"], cwd=target, text=True, capture_output=True)
            if res_pw.returncode != 0:
                raise Exception(f"Falha ao instalar browser Chromium: {res_pw.stderr}")

            # 5. Atalho
            if self.create_shortcut.get():
                self.after(0, lambda: self.status_lbl.configure(text="A criar atalho na Área de Trabalho..."))
                exe = os.path.join(target, "NetEyeAI.exe")
                
                # Obter path real do Desktop (independente do idioma do Windows ou OneDrive)
                import winreg
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
                    desktop_path = winreg.QueryValueEx(key, "Desktop")[0]
                    desktop_path = os.path.expandvars(desktop_path)
                except Exception:
                    desktop_path = os.path.join(os.environ["USERPROFILE"], "Desktop")
                
                lnk = os.path.join(desktop_path, "NetEyeAI.lnk")
                icon_path = os.path.join(target, "static", "logo.ico")
                
                # Escapar aspas simples para PowerShell
                lnk_escaped = lnk.replace("'", "''")
                pyw_exe_escaped = pyw_exe.replace("'", "''")
                target_escaped = target.replace("'", "''")
                icon_path_escaped = icon_path.replace("'", "''")
                
                if not os.path.exists(exe):
                    script_path = os.path.join(target, "run_gui.py")
                    script_path_escaped = script_path.replace("'", "''")
                    ps = f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_escaped}');$s.TargetPath='{pyw_exe_escaped}';$s.Arguments='\"{script_path_escaped}\"';$s.WorkingDirectory='{target_escaped}';$s.IconLocation='{icon_path_escaped},0';$s.Save()"
                else:
                    exe_escaped = exe.replace("'", "''")
                    ps = f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk_escaped}');$s.TargetPath='{exe_escaped}';$s.WorkingDirectory='{target_escaped}';$s.IconLocation='{icon_path_escaped},0';$s.Save()"
                
                subprocess.run(["powershell", "-Command", ps], capture_output=True)

            self.after(500, lambda: self._show_step(6))
        except Exception as e:
            messagebox.showerror("Erro", f"Falha na instalação: {e}")
            self.after(0, lambda: self._show_step(3))

    def _update_progress(self, pct, msg):
        self.progress_bar.set(pct/100)
        self.pct_lbl.configure(text=f"{pct}%")
        self.status_lbl.configure(text=msg)

    def _next_step(self):
        if self.current_step == 3:
            path = self.path_entry.get().strip()
            if not path.lower().endswith("neteyeai"):
                path = os.path.join(path, "NetEyeAI")
            self.install_path = path
        if self.current_step == 6: return
        self.current_step += 1; self._show_step(self.current_step)

    def _prev_step(self): self.current_step -= 1; self._show_step(self.current_step)
    def _browse_path(self):
        p = filedialog.askdirectory(initialdir=self.install_path)
        if p:
            if not p.lower().endswith("neteyeai"):
                p = os.path.join(p, "NetEyeAI")
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, p)

    def _finish_all(self):
        if self.launch_after.get():
            exe = os.path.join(self.install_path, "NetEyeAI.exe")
            if os.path.exists(exe):
                subprocess.Popen([exe], cwd=self.install_path, shell=True)
            else:
                real_python, pyw_exe = find_python_and_pythonw()
                script_path = os.path.join(self.install_path, "run_gui.py")
                subprocess.Popen([pyw_exe, script_path], cwd=self.install_path)
        self.destroy()

if __name__ == "__main__":
    NetEyeInstaller().mainloop()
