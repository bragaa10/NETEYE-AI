"""
NetEye — core/connection_pool.py (CONNECTION POOLING SUPABASE)
================================================================
Pool de conexões reutilizáveis para Supabase.
Reduz overhead de inicialização de conexões.

Não interfere no funcionamento - apenas otimiza conexões.
"""

import os
import threading
import time
from typing import Optional
from queue import Queue, Empty
from rich.console import Console
from supabase import create_client, Client
from core.credentials import obter_supabase_url, obter_supabase_key

console = Console()


class SupabaseConnectionPool:
    """
    Pool de conexões Supabase thread-safe.
    - Min: 1 conexão
    - Max: 5 conexões
    - Reusa conexões automaticamente
    """
    
    def __init__(self, min_size: int = 1, max_size: int = 5):
        self.min_size = min_size
        self.max_size = max_size
        self._pool: Queue = Queue(maxsize=max_size)
        self._active_count = 0
        self._lock = threading.RLock()
        
        url = obter_supabase_url()
        key = obter_supabase_key()
        
        self._url = url
        self._key = key
        self._initialized = False
        
        if url and key:
            self._inicializar_pool()
    
    def _inicializar_pool(self):
        """Cria conexões iniciais no pool."""
        try:
            for _ in range(self.min_size):
                client = self._criar_conexao()
                if client:
                    self._pool.put(client)
                    # FIX: Contabilizar conexões iniciais no _active_count
                    with self._lock:
                        self._active_count += 1
            self._initialized = True
            console.print(f"[dim green][OK] Pool Supabase pronto ({self.min_size} conexões)[/dim green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Erro ao inicializar pool: {e}[/yellow]")
    
    def _criar_conexao(self) -> Optional[Client]:
        """Cria nova conexão Supabase."""
        try:
            return create_client(self._url, self._key)
        except Exception as e:
            console.print(f"[red]Erro ao criar conexão: {e}[/red]")
            return None
    
    def obter(self, timeout: float = 5.0) -> Optional[Client]:
        """Obtém conexão do pool ou cria nova se necessário."""
        try:
            # Tentar obter do pool sem bloquear
            return self._pool.get_nowait()
        except Empty:
            # Se pool vazio, criar nova conexão se não atingimos limite
            with self._lock:
                if self._active_count < self.max_size:
                    self._active_count += 1
                    client = self._criar_conexao()
                    if client:
                        return client
                    else:
                        self._active_count -= 1
            
            # Se não há conexões ativas criadas (ex: falha de inicialização/rede),
            # não vale a pena esperar na fila, pois nada será devolvido.
            with self._lock:
                if self._active_count == 0:
                    return None
            
            # Bloquear até haver conexão disponível
            try:
                return self._pool.get(timeout=timeout)
            except Empty:
                console.print(f"[yellow]⚠️ Timeout esperando conexão pool ({timeout}s)[/yellow]")
                return None
    
    def devolver(self, client: Client):
        """Devolve conexão ao pool."""
        if client:
            try:
                self._pool.put_nowait(client)
            except Exception:
                # Pool cheio — descartar a conexão e decrementar contagem
                with self._lock:
                    self._active_count = max(0, self._active_count - 1)
                console.print("[dim yellow]⚠️ Pool cheio, conexão descartada[/dim yellow]")
    
    def limpar(self):
        """Limpa todo o pool."""
        while not self._pool.empty():
            try:
                self._pool.get_nowait()
            except Empty:
                break
        with self._lock:
            self._active_count = 0


# Instância global do pool (singleton thread-safe)
_pool_instance: Optional[SupabaseConnectionPool] = None
_pool_lock = threading.Lock()


def obter_pool() -> SupabaseConnectionPool:
    """Obtém a instância global do pool (thread-safe)."""
    global _pool_instance
    if _pool_instance is None:
        with _pool_lock:
            # Double-checked locking
            if _pool_instance is None:
                _pool_instance = SupabaseConnectionPool(min_size=1, max_size=5)
    return _pool_instance


class PooledSupabaseClient:
    """
    Wrapper para usar Supabase com pool de conexões.
    Usa context manager para garantir devolução de conexão.
    """
    
    def __init__(self):
        self.pool = obter_pool()
        self._client = None
    
    def __enter__(self) -> Client:
        self._client = self.pool.obter()
        return self._client
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            self.pool.devolver(self._client)
    
    @staticmethod
    def executar_com_pool(func):
        """Decorator para executar função com pool."""
        def wrapper(*args, **kwargs):
            with PooledSupabaseClient() as client:
                return func(client, *args, **kwargs)
        return wrapper
