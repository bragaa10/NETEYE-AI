"""
NetEye — core/database.py
==========================
Persistência de dados com Supabase (Cloud).
"""

import os
import json
from datetime import datetime
from rich.console import Console
from supabase import create_client, Client

console = Console()


class Database:
    def __init__(self, caminho_legado: str = None):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

        if not url or not key:
            console.print("[bold red]❌ SUPABASE_URL ou SUPABASE_KEY não configuradas no .env[/bold red]")
            self.client = None
        else:
            try:
                self.client: Client = create_client(url, key)
            except Exception as e:
                console.print(f"[bold red]❌ Erro ao ligar à Supabase: {e}[/bold red]")
                self.client = None

    # ------------------------------------------------------------------
    # UTILIZADORES
    # ------------------------------------------------------------------

    def obter_utilizador(self, username: str) -> dict | None:
        if not self.client: return None
        try:
            res = self.client.table("utilizadores").select("id, username, password_hash").eq("username", username).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            console.print(f"[red]Erro ao obter utilizador: {e}[/red]")
            return None

    def atualizar_username(self, user_id: int, novo_username: str) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("utilizadores").update({"username": novo_username}).eq("id", user_id).execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro ao atualizar username: {e}[/red]")
            return False

    def registar_utilizador(self, username: str, password_hash: str) -> int:
        if not self.client: return -1
        try:
            data = {
                "username": username,
                "password_hash": password_hash,
                "data_criacao": datetime.now().isoformat()
            }
            res = self.client.table("utilizadores").insert(data).execute()
            return res.data[0]["id"] if res.data else -1
        except Exception as e:
            console.print(f"[red]Erro ao registar utilizador: {e}[/red]")
            return -1

    # ------------------------------------------------------------------
    # CONFIGURAÇÕES
    # ------------------------------------------------------------------

    def guardar_configuracao(self, user_id: int, chave: str, valor: str) -> bool:
        if not self.client: return False
        try:
            data = {"user_id": user_id, "chave": chave, "valor": str(valor)}
            res = self.client.table("configuracoes").upsert(data, on_conflict="user_id,chave").execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro ao guardar configuração: {e}[/red]")
            return False

    def obter_configuracao(self, user_id: int, chave: str, padrao: str = "") -> str:
        if not self.client: return padrao
        try:
            res = self.client.table("configuracoes").select("valor").eq("user_id", user_id).eq("chave", chave).execute()
            return res.data[0]["valor"] if res.data else padrao
        except Exception:
            return padrao

    def obter_todas_configuracoes(self, user_id: int) -> dict:
        if not self.client: return {}
        try:
            res = self.client.table("configuracoes").select("chave, valor").eq("user_id", user_id).execute()
            return {row["chave"]: row["valor"] for row in res.data}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # FAVORITOS
    # ------------------------------------------------------------------

    def adicionar_favorito(self, user_id: int, nome: str, url: str) -> bool:
        if not self.client: return False
        try:
            data = {
                "user_id": user_id,
                "nome": nome,
                "url": url,
                "data_adicao": datetime.now().isoformat()
            }
            res = self.client.table("favoritos").upsert(data, on_conflict="user_id,url").execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro ao guardar favorito: {e}[/red]")
            return False

    def listar_favoritos(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("favoritos").select("id, nome, url").eq("user_id", user_id).order("nome").execute()
            return res.data
        except Exception:
            return []

    def remover_favorito_por_url(self, user_id: int, url: str) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("favoritos").delete().eq("user_id", user_id).eq("url", url).execute()
            return True if res.data else False
        except Exception:
            return False

    def remover_favorito_por_id(self, user_id: int, id_favorito: int) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("favoritos").delete().eq("user_id", user_id).eq("id", id_favorito).execute()
            return True if res.data else False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # HISTÓRICO DE NAVEGAÇÃO
    # ------------------------------------------------------------------

    def registar_visita(self, user_id: int, url: str, titulo: str = ""):
        if not self.client: return
        try:
            data = {
                "user_id": user_id,
                "url": url,
                "titulo": titulo,
                "data_visita": datetime.now().isoformat()
            }
            self.client.table("historico").insert(data).execute()
        except Exception:
            pass

    def historico_recente(self, user_id: int, limite: int = 10) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("historico").select("url, titulo, data_visita").eq("user_id", user_id).order("data_visita", desc=True).limit(limite).execute()
            return res.data
        except Exception:
            return []

    def historico_completo(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("historico").select("url, titulo, data_visita").eq("user_id", user_id).order("data_visita", desc=True).execute()
            return res.data
        except Exception:
            return []

    def limpar_historico(self, user_id: int) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("historico").delete().eq("user_id", user_id).execute()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # HISTÓRICO DE COMANDOS (Novo - Func 2)
    # ------------------------------------------------------------------

    def registar_comando(self, user_id: int, comando: str, resposta: str = ""):
        if not self.client: return
        try:
            data = {
                "user_id": user_id,
                "comando": comando,
                "resposta": resposta,
                "data_comando": datetime.now().isoformat()
            }
            self.client.table("comando_historico").insert(data).execute()
        except Exception as e:
            console.print(f"[dim red]Erro ao registar comando: {e}[/dim red]")

    def obter_ultimo_comando(self, user_id: int) -> dict | None:
        if not self.client: return None
        try:
            res = self.client.table("comando_historico").select("*").eq("user_id", user_id).order("data_comando", desc=True).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # ATALHOS DE VOZ (Novo - Func 6)
    # ------------------------------------------------------------------

    def adicionar_atalho(self, user_id: int, frase: str, acao: str) -> bool:
        if not self.client: return False
        try:
            data = {"user_id": user_id, "frase": frase.lower(), "acao": acao}
            self.client.table("atalhos").upsert(data, on_conflict="user_id,frase").execute()
            return True
        except Exception:
            return False

    def listar_atalhos(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("atalhos").select("*").eq("user_id", user_id).execute()
            return res.data
        except Exception:
            return []

    def remover_atalho(self, user_id: int, atalho_id: int) -> bool:
        if not self.client: return False
        try:
            self.client.table("atalhos").delete().eq("user_id", user_id).eq("id", atalho_id).execute()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # BLOQUEIOS
    # ------------------------------------------------------------------

    def adicionar_bloqueio(self, user_id: int, url: str) -> bool:
        if not self.client: return False
        try:
            data = {
                "user_id": user_id,
                "url": url,
                "data_bloqueio": datetime.now().isoformat()
            }
            res = self.client.table("bloqueios").insert(data).execute()
            return True if res.data else False
        except Exception:
            return False

    def listar_bloqueios(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("bloqueios").select("id, url, data_bloqueio").eq("user_id", user_id).order("data_bloqueio", desc=True).execute()
            return res.data
        except Exception:
            return []

    def remover_bloqueio_por_url(self, user_id: int, url: str) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("bloqueios").delete().eq("user_id", user_id).eq("url", url).execute()
            return True if res.data else False
        except Exception:
            return False

    def remover_bloqueio_por_id(self, user_id: int, id_bloqueio: int) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("bloqueios").delete().eq("user_id", user_id).eq("id", id_bloqueio).execute()
            return True if res.data else False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # RELATÓRIOS DE SESSÃO (Novo - Func 11)
    # ------------------------------------------------------------------

    def guardar_relatorio_sessao(self, user_id: int, dados: dict):
        if not self.client: return
        try:
            data = {
                "user_id": user_id,
                "dados": json.dumps(dados),
                "data_sessao": datetime.now().isoformat()
            }
            self.client.table("relatorios_sessao").insert(data).execute()
        except Exception as e:
            console.print(f"[dim red]Erro ao guardar relatório: {e}[/dim red]")

    # ------------------------------------------------------------------
    # BACKUP / EXPORT (Func 14)
    # ------------------------------------------------------------------

    def exportar_dados(self, user_id: int) -> dict:
        """Exporta favoritos, bloqueios e atalhos para JSON."""
        return {
            "favoritos": self.listar_favoritos(user_id),
            "bloqueios": self.listar_bloqueios(user_id),
            "atalhos": self.listar_atalhos(user_id),
            "configuracoes": self.obter_todas_configuracoes(user_id)
        }

    # ------------------------------------------------------------------
    # PREFERÊNCIAS (GLOBAIS)
    # ------------------------------------------------------------------

    def guardar_preferencia(self, chave: str, valor: str):
        if not self.client: return
        try:
            data = {"chave": chave, "valor": str(valor)}
            self.client.table("preferencias").upsert(data).execute()
        except Exception:
            pass

    def obter_preferencia(self, chave: str, padrao: str = "") -> str:
        if not self.client: return padrao
        try:
            res = self.client.table("preferencias").select("valor").eq("chave", chave).execute()
            return res.data[0]["valor"] if res.data else padrao
        except Exception:
            return padrao

    def fechar(self):
        pass
