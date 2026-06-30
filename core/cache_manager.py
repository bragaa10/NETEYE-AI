"""
NetEye — core/cache_manager.py (MULTI-LEVEL CACHING)
=====================================================
Sistema de cache em 3 níveis:
1. Memória (rápido, TTL curto)
2. Disco (persistente, TTL longo)
3. DB (índice de URLs visitadas)

Não interfere no funcionamento - apenas melhora performance.
"""

import time
import json
import hashlib
import os
from threading import RLock
from pathlib import Path
from typing import Any, Optional, Tuple
from rich.console import Console

console = Console()


class CacheManager:
    """
    Cache multi-level thread-safe para:
    - Respostas de Claude (30min em memória)
    - Análises de screenshot (1h em memória)
    - Índice de URLs (persistente)
    """
    
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache em memória
        self._memory_cache = {}  # {hash: (valor, timestamp, ttl)}
        self._lock = RLock()
        
        # Ficheiro de índice de URLs
        self._index_file = self.cache_dir / "url_index.json"
        self._url_index = self._carregar_index()
        
        console.print(f"[dim green][OK] CacheManager pronto ({self.cache_dir})[/dim green]")
    
    # ------------------------------------------------------------------
    # CACHE EM MEMÓRIA
    # ------------------------------------------------------------------
    
    def get(self, chave: str, ttl: int = 1800) -> Optional[Any]:
        """Obtém valor do cache (checa expiração)."""
        with self._lock:
            if chave in self._memory_cache:
                valor, timestamp, ttl_stored = self._memory_cache[chave]
                if time.time() - timestamp < ttl_stored:
                    return valor
                else:
                    del self._memory_cache[chave]
        return None
    
    MAX_MEMORY_ENTRIES = 500

    def set(self, chave: str, valor: Any, ttl: int = 1800):
        """Armazena valor no cache com TTL."""
        with self._lock:
            self._memory_cache[chave] = (valor, time.time(), ttl)
            if len(self._memory_cache) > self.MAX_MEMORY_ENTRIES:
                oldest_key = min(self._memory_cache, key=lambda k: self._memory_cache[k][1])
                del self._memory_cache[oldest_key]
    
    def invalidar(self, chave: str):
        """Remove valor do cache."""
        with self._lock:
            if chave in self._memory_cache:
                del self._memory_cache[chave]
    
    def limpar_cache(self):
        """Limpa todo o cache em memória."""
        with self._lock:
            self._memory_cache.clear()
    
    # ------------------------------------------------------------------
    # CACHE DE COMANDOS (Claude)
    # ------------------------------------------------------------------
    
    def cache_comando(self, comando: str, resposta: dict, ttl: int = 1800) -> str:
        """Cria hash do comando e armazena resposta."""
        chave = self._hash_comando(comando)
        self.set(chave, resposta, ttl)
        return chave
    
    def obter_comando_cache(self, comando: str) -> Optional[dict]:
        """Obtém resposta cached de um comando."""
        chave = self._hash_comando(comando)
        return self.get(chave)
    
    @staticmethod
    def _hash_comando(comando: str) -> str:
        """Gera hash SHA256 de um comando."""
        return hashlib.sha256(comando.lower().strip().encode()).hexdigest()[:12]
    
    # ------------------------------------------------------------------
    # CACHE DE SCREENSHOTS
    # ------------------------------------------------------------------
    
    def cache_screenshot_analise(self, url: str, analise: dict, ttl: int = 3600) -> str:
        """Cria hash da análise de screenshot."""
        chave = f"scr_{self._hash_url(url)}"
        self.set(chave, analise, ttl)
        return chave
    
    def obter_screenshot_cache(self, url: str) -> Optional[dict]:
        """Obtém análise cached de screenshot."""
        chave = f"scr_{self._hash_url(url)}"
        return self.get(chave)
    
    # ------------------------------------------------------------------
    # ÍNDICE DE URLs (PERSISTENTE)
    # ------------------------------------------------------------------
    
    def registar_url(self, url: str, titulo: str, metadata: dict = None):
        """Registra URL no índice (evita re-scrapes)."""
        url_hash = self._hash_url(url)
        with self._lock:
            self._url_index[url_hash] = {
                "url": url,
                "titulo": titulo,
                "timestamp": time.time(),
                "metadata": metadata or {}
            }
            self._guardar_index()
    
    def url_já_visitada(self, url: str) -> Tuple[bool, Optional[dict]]:
        """Verifica se URL foi visitada anteriormente."""
        url_hash = self._hash_url(url)
        with self._lock:
            if url_hash in self._url_index:
                info = self._url_index[url_hash]
                # Atualizar timestamp (para manter URLs recentes)
                info["timestamp"] = time.time()
                self._guardar_index()
                return True, info
        return False, None
    
    def listar_urls_recentes(self, limite: int = 20) -> list:
        """Lista URLs visitadas recentemente."""
        with self._lock:
            urls = sorted(
                self._url_index.values(),
                key=lambda x: x.get("timestamp", 0),
                reverse=True
            )
            return urls[:limite]
    
    @staticmethod
    def _hash_url(url: str) -> str:
        """Gera hash SHA256 de uma URL."""
        return hashlib.sha256(url.lower().strip().encode()).hexdigest()[:16]
    
    # ------------------------------------------------------------------
    # PERSISTÊNCIA
    # ------------------------------------------------------------------
    
    def _carregar_index(self) -> dict:
        """Carrega índice de URLs do disco."""
        try:
            if self._index_file.exists():
                with open(self._index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            console.print(f"[yellow]⚠️ Erro ao carregar índice: {e}[/yellow]")
        return {}
    
    def _guardar_index(self):
        """Guarda índice de URLs no disco."""
        try:
            with open(self._index_file, 'w', encoding='utf-8') as f:
                json.dump(self._url_index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            console.print(f"[yellow]⚠️ Erro ao guardar índice: {e}[/yellow]")
    
    def limpar_index_antigo(self, dias: int = 30):
        """Remove URLs não visitadas há mais de N dias."""
        com_limite = time.time() - (dias * 86400)
        with self._lock:
            chaves_antigas = [
                k for k, v in self._url_index.items()
                if v.get("timestamp", 0) < com_limite
            ]
            for chave in chaves_antigas:
                del self._url_index[chave]
            if chaves_antigas:
                self._guardar_index()
                console.print(f"[dim]🧹 Removidas {len(chaves_antigas)} URLs antigas[/dim]")
