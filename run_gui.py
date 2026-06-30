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

# Garantir que o working directory é o diretório do script
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gui.app import NetEyeApp

if __name__ == "__main__":
    # Se houver argumentos de comando, age como o assistente (subprocesso)
    if len(sys.argv) > 1 and ("--assistant" in sys.argv or "--chave-api" in sys.argv):
        if "--assistant" in sys.argv:
            try:
                sys.argv.remove("--assistant")
            except ValueError:
                pass
        import main as assistant_main
        assistant_main.main()
    else:
        # Caso contrário, abre a interface gráfica
        app = NetEyeApp()
        app.mainloop()
