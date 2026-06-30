"""
NetEye — core/database.py
==========================
Persistência de dados com Supabase (Cloud).
[OTIMIZAÇÃO] Integrado com connection pool para melhor performance.
"""

import os
import json
import threading
from datetime import datetime, timezone
from rich.console import Console
from supabase import create_client, Client
from core.credentials import obter_supabase_url, obter_supabase_key, obter_chave_encriptacao

console = Console()

# Importar o pool de conexões (otimização)
try:
    from core.connection_pool import obter_pool, PooledSupabaseClient
    _usar_pool = True
except ImportError:
    _usar_pool = False


def usar_pool(func):
    """Decorator para garantir que a query usa uma conexão do pool se disponível."""
    def wrapper(self, *args, **kwargs):
        if self.pool:
            # Re-entrancy check: if this thread already has a pooled client, reuse it
            old_client = getattr(self._thread_local, "client", None)
            if old_client is not None:
                self.client = old_client
                return func(self, *args, **kwargs)
            with PooledSupabaseClient() as client:
                self._thread_local.client = client
                self.client = client
                try:
                    return func(self, *args, **kwargs)
                finally:
                    self._thread_local.client = None
                    self.client = None
        else:
            return func(self, *args, **kwargs)
    return wrapper


class Database:
    def __init__(self, caminho_legado: str = None):
        self._thread_local = threading.local()
        self._static_client = None
        self.pool = None

        url = obter_supabase_url()
        key = obter_supabase_key()

        if not url or not key:
            console.print("[bold red]❌ SUPABASE_URL ou SUPABASE_KEY não configuradas[/bold red]")
        else:
            try:
                self._static_client = create_client(url, key)
                # Inicializar pool se disponível (otimização)
                if _usar_pool:
                    self.pool = obter_pool()
            except Exception as e:
                console.print(f"[bold red]❌ Erro ao ligar à Supabase: {e}[/bold red]")

    @property
    def client(self) -> Client:
        if hasattr(self._thread_local, "client") and self._thread_local.client is not None:
            return self._thread_local.client
        return self._static_client

    @client.setter
    def client(self, val):
        self._thread_local.client = val

    # ------------------------------------------------------------------
    # UTILIZADORES
    # ------------------------------------------------------------------

    @usar_pool
    def obter_utilizador(self, username: str) -> dict | None:
        if not self.client: return None
        try:
            res = self.client.table("utilizadores").select("id, username, password_hash").eq("username", username).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            console.print(f"[red]Erro ao obter utilizador: {e}[/red]")
            return None

    @usar_pool
    def atualizar_username(self, user_id: int, novo_username: str) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("utilizadores").update({"username": novo_username}).eq("id", user_id).execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro ao atualizar username: {e}[/red]")
            return False

    @usar_pool
    def registar_utilizador(self, username: str, password_hash: str) -> int:
        if not self.client: return -1
        try:
            data = {
                "username": username,
                "password_hash": password_hash,
                "data_criacao": datetime.now(timezone.utc).isoformat()
            }
            res = self.client.table("utilizadores").insert(data).execute()
            return res.data[0]["id"] if res.data else -1
        except Exception as e:
            console.print(f"[red]Erro ao registar utilizador: {e}[/red]")
            return -1

    # ------------------------------------------------------------------
    # CONFIGURAÇÕES E CRIPTOGRAFIA
    # ------------------------------------------------------------------

    def _get_fernet(self):
        """Obtém instância Fernet com chave dedicada."""
        import base64
        import hashlib
        from cryptography.fernet import Fernet
        
        raw = obter_chave_encriptacao()
        if not raw:
            raise EnvironmentError(
                "Chave de encriptação NETEYE_ENCRYPTION_KEY não definida."
            )
        # FIX: Chave de encriptação dedicada e independente da chave Supabase.
        # Permite rodar SUPABASE_KEY sem perder dados encriptados.
        digest = hashlib.sha256(raw.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def _encrypt(self, text: str) -> str:
        if not text:
            return ""
        try:
            f = self._get_fernet()
            return f.encrypt(text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            console.print(f"[red]Erro ao encriptar texto: {e}[/red]")
            raise e

    def _decrypt(self, text: str) -> str:
        if not text:
            return ""
        try:
            f = self._get_fernet()
            return f.decrypt(text.encode('utf-8')).decode('utf-8')
        except Exception:
            # Em caso de falha de decriptação, assume texto limpo
            return text

    @usar_pool
    def esta_disponivel(self) -> bool:
        """Verifica se Supabase está acessível."""
        # FIX: Verificar disponibilidade do Supabase antes de iniciar a sessão.
        if not self.client:
            return False
        try:
            self.client.table("utilizadores").select("id").limit(1).execute()
            return True
        except Exception as e:
            console.print(f"[red]Erro em esta_disponivel: {e}[/red]")
            return False

    @usar_pool
    def guardar_configuracao(self, user_id: int, chave: str, valor: str) -> bool:
        if not self.client: return False
        try:
            if chave == "api_key":
                valor = self._encrypt(valor)
            data = {"user_id": user_id, "chave": chave, "valor": str(valor)}
            res = self.client.table("configuracoes").upsert(data, on_conflict="user_id,chave").execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro ao guardar configuração: {e}[/red]")
            return False

    @usar_pool
    def obter_configuracao(self, user_id: int, chave: str, padrao: str = "") -> str:
        if not self.client: return padrao
        try:
            res = self.client.table("configuracoes").select("valor").eq("user_id", user_id).eq("chave", chave).execute()
            val = res.data[0]["valor"] if res.data else padrao
            if chave == "api_key":
                val = self._decrypt(val)
            return val
        except Exception as e:
            console.print(f"[red]Erro em obter_configuracao: {e}[/red]")
            return padrao

    @usar_pool
    def obter_todas_configuracoes(self, user_id: int) -> dict:
        if not self.client: return {}
        try:
            res = self.client.table("configuracoes").select("chave, valor").eq("user_id", user_id).execute()
            configs = {row["chave"]: row["valor"] for row in res.data}
            if "api_key" in configs:
                configs["api_key"] = self._decrypt(configs["api_key"])
            return configs
        except Exception as e:
            console.print(f"[red]Erro em obter_todas_configuracoes: {e}[/red]")
            return {}

    # ------------------------------------------------------------------
    # FAVORITOS
    # ------------------------------------------------------------------

    @usar_pool
    def adicionar_favorito(self, user_id: int, nome: str, url: str) -> bool:
        if not self.client: return False
        try:
            data = {
                "user_id": user_id,
                "nome": nome,
                "url": url,
                "data_adicao": datetime.now(timezone.utc).isoformat()
            }
            res = self.client.table("favoritos").upsert(data, on_conflict="user_id,url").execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro ao guardar favorito: {e}[/red]")
            return False

    @usar_pool
    def listar_favoritos(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("favoritos").select("id, nome, url").eq("user_id", user_id).order("nome").execute()
            return res.data
        except Exception as e:
            console.print(f"[red]Erro em listar_favoritos: {e}[/red]")
            return []

    @usar_pool
    def remover_favorito_por_url(self, user_id: int, url: str) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("favoritos").delete().eq("user_id", user_id).eq("url", url).execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro em remover_favorito_por_url: {e}[/red]")
            return False

    @usar_pool
    def remover_favorito_por_id(self, user_id: int, id_favorito: int) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("favoritos").delete().eq("user_id", user_id).eq("id", id_favorito).execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro em remover_favorito_por_id: {e}[/red]")
            return False

    # ------------------------------------------------------------------
    # HISTÓRICO DE NAVEGAÇÃO
    # ------------------------------------------------------------------

    @usar_pool
    def registar_visita(self, user_id: int, url: str, titulo: str = ""):
        if not self.client: return
        try:
            data = {
                "user_id": user_id,
                "url": url,
                "titulo": titulo,
                "data_visita": datetime.now(timezone.utc).isoformat()
            }
            self.client.table("historico").insert(data).execute()
        except Exception as e:
            console.print(f"[red]Erro em registar_visita: {e}[/red]")

    @usar_pool
    def historico_recente(self, user_id: int, limite: int = 10) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("historico").select("url, titulo, data_visita").eq("user_id", user_id).order("data_visita", desc=True).limit(limite).execute()
            return res.data
        except Exception as e:
            console.print(f"[red]Erro em historico_recente: {e}[/red]")
            return []

    @usar_pool
    def historico_completo(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("historico").select("url, titulo, data_visita").eq("user_id", user_id).order("data_visita", desc=True).execute()
            return res.data
        except Exception as e:
            console.print(f"[red]Erro em historico_completo: {e}[/red]")
            return []

    @usar_pool
    def limpar_historico(self, user_id: int) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("historico").delete().eq("user_id", user_id).execute()
            return True
        except Exception as e:
            console.print(f"[red]Erro em limpar_historico: {e}[/red]")
            return False

    # ------------------------------------------------------------------
    # HISTÓRICO DE COMANDOS (Novo - Func 2)
    # ------------------------------------------------------------------

    @usar_pool
    def registar_comando(self, user_id: int, comando: str, resposta: str = ""):
        if not self.client: return
        try:
            data = {
                "user_id": user_id,
                "comando": comando,
                "resposta": resposta,
                "data_comando": datetime.now(timezone.utc).isoformat()
            }
            self.client.table("comando_historico").insert(data).execute()
        except Exception as e:
            console.print(f"[dim red]Erro ao registar comando: {e}[/dim red]")

    @usar_pool
    def obter_ultimo_comando(self, user_id: int) -> dict | None:
        if not self.client: return None
        try:
            res = self.client.table("comando_historico").select("*").eq("user_id", user_id).order("data_comando", desc=True).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            console.print(f"[red]Erro em obter_ultimo_comando: {e}[/red]")
            return None

    # ------------------------------------------------------------------
    # ATALHOS DE VOZ (Novo - Func 6)
    # ------------------------------------------------------------------

    @usar_pool
    def adicionar_atalho(self, user_id: int, frase: str, acao: str) -> bool:
        if not self.client: return False
        try:
            data = {"user_id": user_id, "frase": frase.lower(), "acao": acao}
            self.client.table("atalhos").upsert(data, on_conflict="user_id,frase").execute()
            return True
        except Exception as e:
            console.print(f"[red]Erro em adicionar_atalho: {e}[/red]")
            return False

    @usar_pool
    def listar_atalhos(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("atalhos").select("*").eq("user_id", user_id).execute()
            return res.data
        except Exception as e:
            console.print(f"[red]Erro em listar_atalhos: {e}[/red]")
            return []

    @usar_pool
    def remover_atalho(self, user_id: int, atalho_id: int) -> bool:
        if not self.client: return False
        try:
            self.client.table("atalhos").delete().eq("user_id", user_id).eq("id", atalho_id).execute()
            return True
        except Exception as e:
            console.print(f"[red]Erro em remover_atalho: {e}[/red]")
            return False

    # ------------------------------------------------------------------
    # BLOQUEIOS
    # ------------------------------------------------------------------

    @usar_pool
    def adicionar_bloqueio(self, user_id: int, url: str) -> bool:
        if not self.client: return False
        try:
            data = {
                "user_id": user_id,
                "url": url,
                "data_bloqueio": datetime.now(timezone.utc).isoformat()
            }
            res = self.client.table("bloqueios").insert(data).execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro em adicionar_bloqueio: {e}[/red]")
            return False

    @usar_pool
    def listar_bloqueios(self, user_id: int) -> list[dict]:
        if not self.client: return []
        try:
            res = self.client.table("bloqueios").select("id, url, data_bloqueio").eq("user_id", user_id).order("data_bloqueio", desc=True).execute()
            return res.data
        except Exception as e:
            console.print(f"[red]Erro em listar_bloqueios: {e}[/red]")
            return []

    @usar_pool
    def remover_bloqueio_por_url(self, user_id: int, url: str) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("bloqueios").delete().eq("user_id", user_id).eq("url", url).execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro em remover_bloqueio_por_url: {e}[/red]")
            return False

    @usar_pool
    def remover_bloqueio_por_id(self, user_id: int, id_bloqueio: int) -> bool:
        if not self.client: return False
        try:
            res = self.client.table("bloqueios").delete().eq("user_id", user_id).eq("id", id_bloqueio).execute()
            return True if res.data else False
        except Exception as e:
            console.print(f"[red]Erro em remover_bloqueio_por_id: {e}[/red]")
            return False

    # ------------------------------------------------------------------
    # RELATÓRIOS DE SESSÃO (Novo - Func 11)
    # ------------------------------------------------------------------

    @usar_pool
    def guardar_relatorio_sessao(self, user_id: int, dados: dict):
        if not self.client: return
        try:
            data = {
                "user_id": user_id,
                "dados": json.dumps(dados),
                "data_sessao": datetime.now(timezone.utc).isoformat()
            }
            self.client.table("relatorios_sessao").insert(data).execute()
        except Exception as e:
            console.print(f"[dim red]Erro ao guardar relatório: {e}[/dim red]")

    # ------------------------------------------------------------------
    # BACKUP / EXPORT (Func 14)
    # ------------------------------------------------------------------

    @usar_pool
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

    @usar_pool
    def guardar_preferencia(self, chave: str, valor: str):
        if not self.client: return
        try:
            data = {"chave": chave, "valor": str(valor)}
            self.client.table("preferencias").upsert(data).execute()
        except Exception as e:
            console.print(f"[red]Erro em guardar_preferencia: {e}[/red]")

    @usar_pool
    def obter_preferencia(self, chave: str, padrao: str = "") -> str:
        if not self.client: return padrao
        try:
            res = self.client.table("preferencias").select("valor").eq("chave", chave).execute()
            return res.data[0]["valor"] if res.data else padrao
        except Exception as e:
            console.print(f"[red]Erro em obter_preferencia: {e}[/red]")
            return padrao

    def fechar(self):
        """Supabase usa HTTP — não há conexão persistente para fechar.
        # FIX: Documentar explicitamente que não há cleanup necessário."""
        pass
