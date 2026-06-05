import os
import sys

# Garantir que o diretório raiz está no path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gui.app import NetEyeApp
import main as assistant_main

if __name__ == "__main__":
    # Se houver argumentos de comando, age como o assistente (subprocesso)
    if len(sys.argv) > 1 and "--chave-api" in sys.argv:
        assistant_main.main()
    else:
        # Caso contrário, abre a interface gráfica
        app = NetEyeApp()
        app.mainloop()
