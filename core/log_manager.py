"""
NetEye — core/log_manager.py (LOG ROTATION & COMPRESSION)
==========================================================
Sistema de logging com:
- Rotação automática (10MB por ficheiro)
- Máximo 5 ficheiros (antigos comprimidos)
- Nível INFO em produção, DEBUG em desenvolvimento
- Compressão gzip de logs antigos

Não interfere no funcionamento - apenas gerencia logs.
"""

import os
import logging
import logging.handlers
import gzip
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console

console = Console()


class LogManager:
    """
    Gerenciador de logs com rotação e compressão.
    """
    
    def __init__(self, log_dir: str = "data/logs", max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        """
        Args:
            log_dir: Diretório para ficheiros de log
            max_bytes: Tamanho máximo de cada ficheiro (10MB default)
            backup_count: Número máximo de ficheiros backup (antigos comprimidos)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        
        # Determinar nível de logging
        self.debug_mode = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = logging.DEBUG if self.debug_mode else logging.INFO
        
        # Criar formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Configurar logger raiz
        self.logger = logging.getLogger('neteye')
        self.logger.setLevel(self.log_level)
        
        # Handler com rotação
        log_file = self.log_dir / 'neteye.log'
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Handler para console também
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.WARNING)  # Console apenas warnings/errors
        self.logger.addHandler(console_handler)
        
        console.print(f"[dim green][OK] LogManager pronto ({log_dir})[/dim green]")
        
        # Limpar logs antigos na inicialização
        self._comprimir_logs_antigos()
    
    def debug(self, msg: str, **kwargs):
        """Log level DEBUG."""
        self.logger.debug(msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        """Log level INFO."""
        self.logger.info(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        """Log level WARNING."""
        self.logger.warning(msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        """Log level ERROR."""
        self.logger.error(msg, **kwargs)
    
    def critical(self, msg: str, **kwargs):
        """Log level CRITICAL."""
        self.logger.critical(msg, **kwargs)
    
    def _comprimir_logs_antigos(self):
        """Comprime ficheiros de log antigos."""
        log_files = sorted(self.log_dir.glob('neteye.log.*'))
        
        for log_file in log_files:
            if not str(log_file).endswith('.gz'):
                try:
                    gz_file = f"{log_file}.gz"
                    with open(log_file, 'rb') as f_in:
                        with gzip.open(gz_file, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(log_file)
                    console.print(f"[dim]📦 Comprimido: {log_file.name} → {Path(gz_file).name}[/dim]")
                except Exception as e:
                    console.print(f"[yellow]⚠️ Erro ao comprimir log: {e}[/yellow]")
        
        # Remover ficheiros de backup antigos (manter apenas backup_count)
        all_gz_files = sorted(self.log_dir.glob('neteye.log.*.gz'), reverse=True)
        for old_file in all_gz_files[self.backup_count:]:
            try:
                os.remove(old_file)
                console.print(f"[dim]🗑️ Removido log antigo: {old_file.name}[/dim]")
            except Exception as e:
                console.print(f"[yellow]⚠️ Erro ao remover log antigo: {e}[/yellow]")
    
    def limpar_logs(self, dias: int = 30):
        """Remove logs com mais de N dias."""
        import time
        limite = time.time() - (dias * 86400)
        
        for log_file in self.log_dir.glob('neteye.log*'):
            if os.path.getmtime(log_file) < limite:
                try:
                    os.remove(log_file)
                    console.print(f"[dim]🗑️ Removido log antigo: {log_file.name}[/dim]")
                except Exception as e:
                    console.print(f"[yellow]⚠️ Erro ao remover: {e}[/yellow]")
    
    def obter_stats(self) -> dict:
        """Retorna estatísticas dos logs."""
        total_size = 0
        file_count = 0
        
        for log_file in self.log_dir.glob('neteye.log*'):
            total_size += os.path.getsize(log_file)
            file_count += 1
        
        return {
            "ficheiros": file_count,
            "tamanho_mb": round(total_size / (1024 * 1024), 2),
            "diretorio": str(self.log_dir),
            "debug_mode": self.debug_mode
        }


# Instância global
_log_manager: Optional[LogManager] = None


def obter_logger() -> LogManager:
    """Obtém a instância global do LogManager."""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager()
    return _log_manager
