"""
NetEye — core/async_io.py (PARALLELIZAÇÃO I/O)
================================================
Sistema para paralelizar chamadas de I/O:
- Claude (processamento de comandos)
- ElevenLabs (síntese de voz)

Não interfere no funcionamento - apenas executa em paralelo.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Any, Optional, Tuple
from rich.console import Console

console = Console()


class AsyncIOManager:
    """
    Gerenciador de I/O paralelo thread-safe.
    Permite executar múltiplas operações de I/O em paralelo sem bloquear.
    """
    
    def __init__(self, max_workers: int = 4):
        """
        Args:
            max_workers: Número máximo de threads executoras
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.max_workers = max_workers
    
    def executar_paralelo(self, tarefas: list) -> dict:
        """
        Executa múltiplas tarefas em paralelo.
        
        Args:
            tarefas: Lista de dicts com:
                - 'nome': identificador único
                - 'funcao': callable to execute
                - 'args': tuple de argumentos (opcional)
                - 'kwargs': dict de argumentos nomeados (opcional)
        
        Returns:
            {nome: (resultado, erro)} - None em caso de erro
        """
        futures = {}
        resultados = {}
        erros = {}
        
        # Submeter todas as tarefas
        for tarefa in tarefas:
            nome = tarefa.get('nome')
            funcao = tarefa.get('funcao')
            args = tarefa.get('args', ())
            kwargs = tarefa.get('kwargs', {})
            
            if nome and funcao:
                future = self.executor.submit(funcao, *args, **kwargs)
                futures[nome] = future
        
        # Aguardar resultados (com timeout)
        for nome, future in futures.items():
            try:
                resultado = future.result(timeout=30)
                resultados[nome] = resultado
            except Exception as e:
                erros[nome] = str(e)
                console.print(f"[yellow]⚠️ Erro na tarefa {nome}: {e}[/yellow]")
        
        return {"resultados": resultados, "erros": erros}
    
    def executar_paralelo_tts(self, claude_task: Callable, tts_task: Callable) -> Tuple[Any, Any]:
        """
        Paraleliza especificamente Claude + TTS.
        Executa ambas em paralelo e retorna resultados em ordem.
        
        Returns:
            (resposta_claude, audio_tts)
        """
        tarefas = [
            {"nome": "claude", "funcao": claude_task},
            {"nome": "tts", "funcao": tts_task}
        ]
        
        resultados = self.executar_paralelo(tarefas)
        
        claude_resp = resultados["resultados"].get("claude")
        tts_resp = resultados["resultados"].get("tts")
        
        if "claude" in resultados["erros"]:
            console.print(f"[red]❌ Erro Claude: {resultados['erros']['claude']}[/red]")
        if "tts" in resultados["erros"]:
            console.print(f"[red]❌ Erro TTS: {resultados['erros']['tts']}[/red]")
        
        return claude_resp, tts_resp
    
    def executar_com_timeout(self, funcao: Callable, args: tuple = (), 
                            kwargs: dict = None, timeout: float = 30) -> Tuple[bool, Any]:
        """
        Executa função com timeout.
        
        Returns:
            (sucesso, resultado/erro)
        """
        kwargs = kwargs or {}
        future = self.executor.submit(funcao, *args, **kwargs)
        
        try:
            resultado = future.result(timeout=timeout)
            return True, resultado
        except Exception as e:
            return False, str(e)
    
    def aguardar_multiplas(self, futures: dict, timeout: float = 30) -> dict:
        """Aguarda múltiplos futures com timeout compartilhado."""
        resultados = {}
        for nome, future in futures.items():
            try:
                resultado = future.result(timeout=timeout)
                resultados[nome] = (True, resultado)
            except Exception as e:
                resultados[nome] = (False, str(e))
        return resultados
    
    def parar(self):
        """Para o executor e aguarda conclusão de tarefas."""
        self.executor.shutdown(wait=True)


# Instância global
_async_manager: Optional[AsyncIOManager] = None


def obter_async_manager() -> AsyncIOManager:
    """Obtém a instância global do AsyncIOManager."""
    global _async_manager
    if _async_manager is None:
        _async_manager = AsyncIOManager(max_workers=4)
    return _async_manager


class ParallelTTSExecutor:
    """
    Executor especializado para paralelizar Claude + TTS.
    Útil no loop principal de processamento de comandos.
    """
    
    def __init__(self, claude_func: Callable, tts_func: Callable):
        """
        Args:
            claude_func: Função que processa com Claude
            tts_func: Função que faz TTS
        """
        self.claude_func = claude_func
        self.tts_func = tts_func
        self.manager = obter_async_manager()
    
    def executar(self, comando: str) -> Tuple[Optional[str], Optional[bytes]]:
        """
        Executa Claude e TTS em paralelo.
        
        Returns:
            (resposta_texto, audio_bytes)
        """
        
        # Preparar tarefas
        tarefas = [
            {"nome": "claude", "funcao": self.claude_func, "args": (comando,)},
            {"nome": "tts", "funcao": self.tts_func}
        ]
        
        resultado = self.manager.executar_paralelo(tarefas)
        
        resposta = resultado["resultados"].get("claude")
        audio = resultado["resultados"].get("tts")
        
        return resposta, audio
