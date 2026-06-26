"""
NetEye — core/credentials.py (PRE-BUNDLED CREDENTIALS)
=====================================================
Credenciais pré-empacotadas de produção para Supabase e encriptação.
Evita a necessidade de ficheiro .env em produção e esconde chaves do utilizador.
"""

import os

# Credenciais de produção padrão (enviadas pré-empacotadas)
SUPABASE_URL_DEFAULT = "https://cctwygvfrifxxsswkubb.supabase.co"
SUPABASE_KEY_DEFAULT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNjdHd5Z3ZmcmlmeHhzc3drdWJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODI0ODY1MjQsImV4cCI6MjA5ODA2MjUyNH0.qipP3ZrAdyYvAs2uD3wAs96Vyc0KxSXkAV68gb5LYZI"
NETEYE_ENCRYPTION_KEY_DEFAULT = "9aefc6183e201b17b2f4f2cd4a38096c4b12574e892cda191e704e6c38fe31f9"


def obter_supabase_url() -> str:
    """Retorna URL do Supabase, priorizando variável de ambiente."""
    return os.environ.get("SUPABASE_URL", SUPABASE_URL_DEFAULT).strip()


def obter_supabase_key() -> str:
    """Retorna Chave Anon do Supabase, priorizando variável de ambiente."""
    return os.environ.get("SUPABASE_KEY", SUPABASE_KEY_DEFAULT).strip()


def obter_chave_encriptacao() -> str:
    """Retorna Chave de Encriptação local, priorizando variável de ambiente."""
    return os.environ.get("NETEYE_ENCRYPTION_KEY", NETEYE_ENCRYPTION_KEY_DEFAULT).strip()
