import os
import subprocess
import threading
import json
import time
import sys
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Carregar ambiente para Supabase
load_dotenv()

from core.database import Database
from core.eleven_speaker import ElevenSpeaker


app = Flask(__name__)
app.config["SECRET_KEY"] = "neteye_super_secret_key"
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db = Database()

# Estado Global do Assistente
assistant_process = None
process_logs = []

def get_db():
    return db

# ------------------------------------------------------------------
# MIDDLEWARE E HELPERS
# ------------------------------------------------------------------

@app.context_processor
def inject_user():
    return dict(user=session.get("username"), user_id=session.get("user_id"))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ------------------------------------------------------------------
# AUTENTICAÇÃO
# ------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = db.obter_utilizador(username)
        
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        
        return render_template("login.html", error="Credenciais inválidas.")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        api_key = request.form.get("api_key")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")
        
        if not username or not api_key.startswith("sk-ant-"):
            return render_template("register.html", error="Dados inválidos. A chave API deve começar por 'sk-ant-'.")
        
        if len(password) < 6:
            return render_template("register.html", error="A senha deve ter pelo menos 6 caracteres.")
            
        if password != confirm:
            return render_template("register.html", error="As senhas não coincidem.")
        
        pw_hash = generate_password_hash(password)
        user_id = db.registar_utilizador(username, pw_hash)
        
        if user_id > 0:
            db.guardar_configuracao(user_id, "api_key", api_key)
            # Configurações padrão
            db.guardar_configuracao(user_id, "velocidade", "135")
            db.guardar_configuracao(user_id, "volume", "100")
            db.guardar_configuracao(user_id, "talker_ativo", "True")
            db.guardar_configuracao(user_id, "guardar_historico", "True")
            db.guardar_configuracao(user_id, "modo_headless", "False")
            return redirect(url_for("login"))
            
        return render_template("register.html", error="Erro ao registar ou utilizador já existe.")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------------------------------------------------------
# DASHBOARD E SSE
# ------------------------------------------------------------------

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    stats = {
        "comandos": len(db.historico_completo(user_id)),
        "favoritos": len(db.listar_favoritos(user_id)),
        "bloqueados": len(db.listar_bloqueios(id_utilizador=user_id))
    }
    recent = db.historico_recente(user_id, limite=10)
    return render_template("dashboard.html", stats=stats, recent=recent, running=(assistant_process is not None))

@app.route("/api/start")
@login_required
def start_assistant():
    global assistant_process, process_logs
    
    # Verificar se processo anterior ainda está rodando
    if assistant_process and assistant_process.poll() is None:
        assistant_process.terminate()
        try:
            assistant_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            assistant_process.kill()
    
    if assistant_process is None or assistant_process.poll() is not None:
        user_id = session["user_id"]
        api_key = db.obter_configuracao(user_id, "api_key")
        
        # Validar se API key está configurada
        if not api_key or not api_key.strip():
            return jsonify({"status": "error", 
                           "message": "Configure a chave de API em Definições primeiro"})
        
        headless = db.obter_configuracao(user_id, "modo_headless", "False") == "True"
        
        # Usar o Python do venv explicitamente
        venv_python = os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "python.exe")
        cmd = [venv_python, "main.py", "--chave-api", api_key, "--user-id", str(user_id)]
        if headless:
            cmd.append("--headless")
        
        try:
            assistant_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
                # Forçar UTF-8 para o subprocesso
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}


            )
            process_logs = []
            return jsonify({"status": "started"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    return jsonify({"status": "already_running"})

@app.route("/api/stop")
@login_required
def stop_assistant():
    global assistant_process
    if assistant_process:
        assistant_process.terminate()
        assistant_process = None
        return jsonify({"status": "stopped"})
    return jsonify({"status": "not_running"})

@app.route("/logs")
@login_required
def stream_logs():
    def generate():
        global assistant_process, process_logs
        if assistant_process:
            while assistant_process and assistant_process.poll() is None:
                line = assistant_process.stdout.readline()
                if line:
                    log_entry = {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "text": line.strip()
                    }
                    yield f"data: {json.dumps(log_entry)}\n\n"
                else:
                    time.sleep(0.1)
            # Enviar log final se o processo terminou
            yield f"data: {json.dumps({'time': datetime.now().strftime('%H:%M:%S'), 'text': '--- Assistant Stopped ---'})}\n\n"
        else:
            yield f"data: {json.dumps({'time': datetime.now().strftime('%H:%M:%S'), 'text': 'Waiting for assistant to start...'})}\n\n"

    return Response(generate(), mimetype="text/event-stream")

# ------------------------------------------------------------------
# CONFIGURAÇÕES E API
# ------------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user_id = session["user_id"]
    if request.method == "POST":
        print(f"\n=== SALVANDO CONFIGURAÇÕES para user_id={user_id} ===")
        
        # Campos booleanos (checkboxes)
        boolean_keys = ["talker_ativo", "interromper_ao_falar", "guardar_historico", "modo_headless"]
        for key in boolean_keys:
            val = request.form.get(key)
            db.guardar_configuracao(user_id, key, "True" if val else "False")
        
        # Campos de texto e números (ignorar se vazios)
        text_keys = ["api_key", "velocidade", "volume", "voz_local"]
        for key in text_keys:
            val = request.form.get(key, "").strip()
            if val:  # Só salva se não estiver vazio
                db.guardar_configuracao(user_id, key, val)
        
        # Alterar username
        new_username = request.form.get("username", "").strip()
        if new_username:
            db.atualizar_username(user_id, new_username)
            session["username"] = new_username

        print("=== CONFIGURAÇÕES GUARDADAS ===\n")
        return redirect(url_for("settings", success=True))

    configs = db.obter_todas_configuracoes(user_id)
    return render_template("settings.html", configs=configs)

@app.route("/api/voices")
def get_voices():
    try:
        import pyttsx3
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            if voices is None:
                voices = []
            v_list = [{"id": v.id, "name": v.name} for v in voices]
            return jsonify(v_list)
        except Exception as e:
            print(f"Erro ao inicializar pyttsx3: {e}")
            return jsonify([])
    except ImportError:
        # pyttsx3 não está instalado
        print("pyttsx3 não está instalado")
        return jsonify([])

@app.route("/api/test-voice")
@login_required
def test_voice():
    user_id = session["user_id"]
    configs = db.obter_todas_configuracoes(user_id)
    # Aqui usaríamos o eleven_speaker ou algo similar para testar
    # Para o teste, usamos o pyttsx3 diretamente via ElevenSpeaker fallback
    try:
        from core.eleven_speaker import ElevenSpeaker
        speaker = ElevenSpeaker({"voice_id": configs.get("voz_id")}) # Config básica
        speaker.falar("Teste de voz do NetEye bem sucedido.")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)})

# ------------------------------------------------------------------
# FAVORITOS, BLOQUEADOS, HISTÓRICO
# ------------------------------------------------------------------

@app.route("/favorites", methods=["GET", "POST"])
@login_required
def favorites():
    user_id = session["user_id"]
    if request.method == "POST":
        name = request.form.get("name")
        url = request.form.get("url")
        db.adicionar_favorito(user_id, name, url)
        return redirect(url_for("favorites"))
    
    favs = db.listar_favoritos(user_id)
    return render_template("favorites.html", favorites=favs)

@app.route("/favorites/delete/<int:id>")
@login_required
def delete_favorite(id):
    db.remover_favorito_por_id(session["user_id"], id)
    return redirect(url_for("favorites"))

@app.route("/blocked", methods=["GET", "POST"])
@login_required
def blocked():
    user_id = session["user_id"]
    if request.method == "POST":
        domain = request.form.get("domain")
        db.adicionar_bloqueio(user_id, domain)
        return redirect(url_for("blocked"))
    
    blocks = db.listar_bloqueios(user_id)
    return render_template("blocked.html", blocked=blocks)

@app.route("/blocked/delete/<int:id>")
@login_required
def delete_blocked(id):
    db.remover_bloqueio_por_id(session["user_id"], id)
    return redirect(url_for("blocked"))

@app.route("/history")
@login_required
def history():
    user_id = session["user_id"]
    hist = db.historico_completo(user_id)
    return render_template("history.html", history=hist)

@app.route("/history/clear")
@login_required
def clear_history():
    db.limpar_historico(session["user_id"])
    return redirect(url_for("history"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
