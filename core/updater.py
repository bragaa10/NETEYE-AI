"""
NetEye — core/updater.py (SISTEMA DE ATUALIZAÇÃO)
=================================================
Verifica novas versões (Releases) no GitHub.
"""

import os
import requests
from rich.console import Console

console = Console()

class Updater:
    def __init__(self, repo_owner: str, repo_name: str, current_version: str):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version.strip().lower()
        self.latest_release = None

    def _is_newer(self, remote_tag: str) -> bool:
        def parse_ver(v):
            v = v.strip().lower().lstrip('v')
            parts = []
            for p in v.split('.'):
                try: parts.append(int(p))
                except ValueError: parts.append(0)
            return parts
        return parse_ver(remote_tag) > parse_ver(self.current_version)

    def verificar_atualizacao(self) -> dict:
        """
        Consulta a API do GitHub por releases.
        Retorna: {"update": bool, "version": str, "url": str, "notes": str}
        """
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
        try:
            res = requests.get(url, headers={"User-Agent": "NetEye-Updater/1.0"}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                tag = data["tag_name"].strip().lower()
                
                if self._is_newer(tag):
                    self.latest_release = data
                    return {
                        "update": True,
                        "version": tag,
                        "url": data["html_url"],
                        "notes": data.get("body", "")
                    }
            return {"update": False}
        except Exception as e:
            console.print(f"[dim red]Erro ao verificar atualizações: {e}[/dim red]")
            return {"update": False}

    def obter_changelog(self) -> str:
        if self.latest_release:
            return self.latest_release.get("body", "Sem notas de lançamento.")
        return ""
