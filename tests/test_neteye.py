import os
import sys
import tempfile
import unittest
import json
import wave
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import numpy as np

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

# Adicionar raiz ao path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Configurar variáveis de ambiente mock para testes
os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
os.environ["SUPABASE_KEY"] = "mock-key-123"
os.environ["NETEYE_ENCRYPTION_KEY"] = "mock-encryption-key-12345678"

from core.database import Database, usar_pool
from core.listener import Listener
from core.eleven_speaker import ElevenSpeaker
from core.talker import Talker
from core.assistant import Assistant
from core.vision import Vision
from core.cache_manager import CacheManager
from core.connection_pool import SupabaseConnectionPool, obter_pool, PooledSupabaseClient
from core.transcriber import _aplicar_correcoes
from core.browser import BrowserController


class TestNetEyeDatabase(unittest.TestCase):
    @patch('core.database.create_client')
    def test_encryption_decryption(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        db = Database()
        
        test_key = "sk-ant-testkey123"
        encrypted = db._encrypt(test_key)
        
        self.assertNotEqual(test_key, encrypted)
        self.assertTrue(encrypted.startswith("gAAAAA"))
        
        decrypted = db._decrypt(encrypted)
        self.assertEqual(test_key, decrypted)
        
        # Testar texto limpo (não criptografado)
        self.assertEqual("sk-ant-plain", db._decrypt("sk-ant-plain"))
        self.assertEqual("", db._decrypt(""))

    @patch('core.database.create_client')
    def test_decrypt_invalid_tokens_fallback(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        db = Database()
        # gAAAAA com formato inválido deve fazer fallback seguro para texto limpo
        self.assertEqual("gAAAAA_invalid", db._decrypt("gAAAAA_invalid"))

    @patch('core.database.create_client')
    def test_guardar_configuracao_api_key(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        db = Database()
        db.client = mock_client
        
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        
        db.guardar_configuracao(1, "api_key", "sk-ant-mykey")
        args, kwargs = mock_table.upsert.call_args
        data = args[0]
        self.assertTrue(data["valor"].startswith("gAAAAA"))
        self.assertEqual(data["chave"], "api_key")
        
        db.guardar_configuracao(1, "volume", "80")
        args, kwargs = mock_table.upsert.call_args
        data = args[0]
        self.assertEqual(data["valor"], "80")

    @patch('core.database.create_client')
    def test_usar_pool_decorator_reentrancy(self, mock_create_client):
        # Testar reentrância do decorator usar_pool
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        class MockDB:
            def __init__(self):
                self.pool = MagicMock()
                self._thread_local = threading_local_mock()
                self.client = None
                self.calls = 0

            @usar_pool
            def metodo_a(self):
                self.calls += 1
                return self.metodo_b()

            @usar_pool
            def metodo_b(self):
                self.calls += 1
                return self.client

        # Mock simple thread local
        class threading_local_mock:
            pass

        db_mock = MockDB()
        
        # Simular PooledSupabaseClient context manager
        mock_pooled_client = MagicMock()
        with patch('core.database.PooledSupabaseClient') as mock_pooled_class:
            mock_pooled_class.return_value.__enter__.return_value = mock_pooled_client
            client_retornado = db_mock.metodo_a()
            
            # Deve chamar metodo_a e metodo_b
            self.assertEqual(db_mock.calls, 2)
            # Deve retornar o mock_pooled_client
            self.assertEqual(client_retornado, mock_pooled_client)
            # A classe PooledSupabaseClient deve ter sido instanciada apenas uma vez (reentrância ativa!)
            self.assertEqual(mock_pooled_class.call_count, 1)


class TestNetEyeListener(unittest.TestCase):
    def test_get_vad_bytes_normalization(self):
        config = {
            "aggressividade": 2,
            "silencio_para_processar": 0.8,
            "tempo_minimo_fala": 0.3,
            "usar_wake_word": False
        }
        listener = Listener(config)
        expected_len = listener.frame_size * 2 # 480 * 2 = 960 bytes
        
        short_frame = np.zeros(300, dtype=np.int16)
        res_bytes = listener._get_vad_bytes(short_frame)
        self.assertEqual(len(res_bytes), expected_len)
        
        long_frame = np.zeros(600, dtype=np.int16)
        res_bytes = listener._get_vad_bytes(long_frame)
        self.assertEqual(len(res_bytes), expected_len)
        
        exact_frame = np.zeros(480, dtype=np.int16)
        res_bytes = listener._get_vad_bytes(exact_frame)
        self.assertEqual(len(res_bytes), expected_len)

    def test_guardar_wav_leak_cleanup(self):
        config = {"aggressividade": 1, "silencio_para_processar": 0.5, "tempo_minimo_fala": 0.2}
        listener = Listener(config)
        
        # wave.open levanta exceção se o path/formato for inválido ou forçado a dar erro
        with patch('wave.open', side_effect=Exception("WAV Error")):
            frames = [np.zeros(480, dtype=np.int16)]
            res = listener._guardar_wav(frames)
            self.assertIsNone(res)


class TestNetEyeSpeaker(unittest.TestCase):
    @patch('core.eleven_speaker.ElevenLabs')
    def test_volume_speed_limits(self, mock_elevenlabs):
        config = {
            "rate": 160,
            "volume": 1.0,
            "idioma": "pt-PT"
        }
        speaker = ElevenSpeaker(config)
        
        speaker.ajustar_volume(0.5) # 1.5
        self.assertAlmostEqual(speaker.volume, 1.5)
        
        speaker.ajustar_volume(1.0) # 2.5 -> limita a 2.0
        self.assertAlmostEqual(speaker.volume, 2.0)
        
        speaker.ajustar_volume(-3.0) # -> limita a 0.0
        self.assertAlmostEqual(speaker.volume, 0.0)
        
        speaker.ajustar_velocidade(50) # 210
        self.assertEqual(speaker.rate, 210)
        
        speaker.ajustar_velocidade(300) # 510 -> limita a 400
        self.assertEqual(speaker.rate, 400)
        
        speaker.ajustar_velocidade(-500) # -> limita a 50
        self.assertEqual(speaker.rate, 50)

    @patch('core.eleven_speaker.ElevenLabs')
    def test_mudar_idioma(self, mock_elevenlabs):
        speaker = ElevenSpeaker({"idioma": "pt-PT"})
        speaker.mudar_idioma("en-US")
        self.assertEqual(speaker.idioma, "en-US")


class TestNetEyeTalker(unittest.TestCase):
    def test_talker_silent_under_2s_on_default(self):
        falar_mock = MagicMock()
        talker = Talker(falar_mock)
        
        talker.iniciar_comando("default")
        talker.parar()
        
        falar_mock.assert_not_called()

    def test_talker_immediate_cues_on_tool(self):
        falar_mock = MagicMock()
        talker = Talker(falar_mock)
        
        talker.iniciar_comando("navegar")
        time.sleep(0.1)
        talker.parar()
        
        falar_mock.assert_called()


class TestNetEyeAssistant(unittest.TestCase):
    @patch('anthropic.Anthropic')
    def test_multi_tool_execution(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        mock_msg = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        
        class MockText:
            type = "text"
            text = "Vou preencher o campo e submeter."
        class MockToolUse:
            def __init__(self, id, name, input):
                self.id = id
                self.type = "tool_use"
                self.name = name
                self.input = input
        
        mock_msg.content = [
            MockText(),
            MockToolUse("tool-1", "escrever", {"texto": "ajuda"}),
            MockToolUse("tool-2", "pressionar_enter", {})
        ]
        
        assistant = Assistant({"assistente": {"talker_ativo": False}}, api_key="sk-ant-test")
        assistant.client = mock_client
        
        tool1_cb = MagicMock(return_value={"ok": True})
        tool2_cb = MagicMock(return_value={"ok": True})
        
        assistant.registar_ferramenta("escrever", tool1_cb)
        assistant.registar_ferramenta("pressionar_enter", tool2_cb)
        
        falar_mock = MagicMock()
        assistant.registar_falar(falar_mock)
        
        mock_msg_final = MagicMock()
        mock_msg_final.content = [MockText()]
        mock_client.messages.create.side_effect = [mock_msg, mock_msg_final]
        
        history = [{"role": "user", "content": "escreve ajuda"}]
        assistant._loop_claude(history, user_id=1)
        
        tool1_cb.assert_called_once_with(texto="ajuda")
        tool2_cb.assert_called_once()
        
        self.assertEqual(len(history), 3)
        self.assertEqual(history[2]["role"], "user")
        self.assertEqual(len(history[2]["content"]), 2)
        self.assertEqual(history[2]["content"][0]["tool_use_id"], "tool-1")
        self.assertEqual(history[2]["content"][1]["tool_use_id"], "tool-2")

    def test_history_pruning(self):
        assistant = Assistant({"assistente": {"talker_ativo": False}}, api_key="sk-ant-test")
        
        long_content = "A" * 1000
        short_content = "curto"
        
        hist = [
            {"role": "user", "content": "olá"},
            {"role": "assistant", "content": "vou ler a página"},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "use-1", "content": long_content}
            ]},
            {"role": "assistant", "content": "outra ação"},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "use-2", "content": short_content}
            ]}
        ]
        
        pruned = assistant._pruning_historico(hist)
        
        self.assertEqual(pruned[-1]["content"][0]["content"], short_content)
        self.assertTrue(len(pruned[2]["content"][0]["content"]) < 600)
        self.assertIn("[Conteúdo truncado", pruned[2]["content"][0]["content"])

    @patch('anthropic.Anthropic')
    def test_runaway_loop_guard(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        class MockToolUse:
            def __init__(self, id, name, input):
                self.id = id
                self.type = "tool_use"
                self.name = name
                self.input = input
                
        mock_msg = MagicMock()
        mock_msg.content = [MockToolUse("tool-1", "clicar", {"texto": "entrar"})]
        mock_client.messages.create.return_value = mock_msg
        
        assistant = Assistant({"assistente": {"talker_ativo": False}}, api_key="sk-ant-test")
        assistant.client = mock_client
        
        tool_cb = MagicMock(return_value={"ok": True})
        assistant.registar_ferramenta("clicar", tool_cb)
        
        falar_mock = MagicMock()
        assistant.registar_falar(falar_mock)
        
        history = [{"role": "user", "content": "clica entrar"}]
        res, tools_called = assistant._loop_claude(history, user_id=1)
        
        self.assertTrue(tools_called)
        self.assertIn("repetidamente sem sucesso", res)
        falar_mock.assert_any_call("Desculpa, percebi que estamos a tentar a mesma ação repetidamente sem sucesso. Podes tentar reformular o pedido?", nao_bloquear=True)
        self.assertTrue(tool_cb.call_count <= 3)

    @patch('anthropic.Anthropic')
    def test_hybrid_model_selection(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        mock_msg = MagicMock()
        mock_msg.content = []
        mock_client.messages.create.return_value = mock_msg
        
        config = {
            "claude": {
                "modelo": "claude-3-5-haiku-20241022",
                "modelo_vision": "claude-3-5-sonnet-20241022",
                "max_tokens": 100
            }
        }
        
        assistant = Assistant(config, api_key="sk-ant-test")
        assistant.client = mock_client
        
        # Caso 1: Pedido simples de navegação -> deve escolher Haiku
        hist_navegacao = [{"role": "user", "content": "navegar para google"}]
        assistant._loop_claude(hist_navegacao, user_id=1)
        args, kwargs = mock_client.messages.create.call_args
        self.assertEqual(kwargs["model"], "claude-3-5-haiku-20241022")
        
        # Caso 2: Pedido com OCR/Visão/Screenshot -> deve escolher Sonnet (modelo_vision)
        hist_vision = [{"role": "user", "content": "ler ecrã com ocr"}]
        assistant._loop_claude(hist_vision, user_id=1)
        args, kwargs = mock_client.messages.create.call_args
        self.assertEqual(kwargs["model"], "claude-3-5-sonnet-20241022")

    @patch('anthropic.Anthropic')
    def test_assistant_tool_error_propagation(self, mock_anthropic):
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        mock_msg = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        
        class MockToolUse:
            def __init__(self, id, name, input):
                self.id = id
                self.type = "tool_use"
                self.name = name
                self.input = input
                
        mock_msg.content = [MockToolUse("tool-fail", "clicar", {"texto": "fado"})]
        
        assistant = Assistant({"assistente": {"talker_ativo": False}}, api_key="sk-ant-test")
        assistant.client = mock_client
        
        tool_cb = MagicMock(return_value={"sucesso": False, "erro": "Elemento não encontrado"})
        assistant.registar_ferramenta("clicar", tool_cb)
        
        falar_mock = MagicMock()
        assistant.registar_falar(falar_mock)
        
        mock_msg_final = MagicMock()
        mock_msg_final.content = []
        mock_client.messages.create.side_effect = [mock_msg, mock_msg_final]
        
        history = [{"role": "user", "content": "clicar fado"}]
        assistant._loop_claude(history, user_id=1)
        
        self.assertEqual(len(history), 3)
        user_response = history[2]
        self.assertEqual(user_response["role"], "user")
        tool_result_item = user_response["content"][0]
        self.assertEqual(tool_result_item["tool_use_id"], "tool-fail")
        self.assertTrue(tool_result_item.get("is_error"))


class TestNetEyeVision(unittest.TestCase):
    @patch('core.vision._obter_reader')
    @patch('cv2.imread')
    @patch('cv2.cvtColor')
    @patch('cv2.threshold')
    @patch('cv2.imwrite')
    def test_vision_extraction_mocked(self, mock_imwrite, mock_threshold, mock_cvtColor, mock_imread, mock_obter_reader):
        mock_reader = MagicMock()
        mock_obter_reader.return_value = mock_reader
        
        mock_reader.readtext.return_value = [
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "Texto detectado no ecrã", 0.9)
        ]
        mock_threshold.return_value = (None, None)
        
        vision = Vision()
        res = vision.extrair_texto_screenshot(caminho_imagem="dummy.png")
        self.assertEqual(res, "Texto detectado no ecrã")

    def test_pagina_tem_conteudo_visual(self):
        vision = Vision()
        self.assertTrue(vision.pagina_tem_conteudo_visual("<html><canvas id='game'></canvas></html>"))
        self.assertFalse(vision.pagina_tem_conteudo_visual("<html><p>Apenas texto normal</p></html>"))

    @patch('core.vision._obter_reader')
    @patch('cv2.imread')
    @patch('cv2.cvtColor')
    @patch('cv2.threshold')
    @patch('cv2.imwrite')
    def test_vision_extraction_mocked_2tuple(self, mock_imwrite, mock_threshold, mock_cvtColor, mock_imread, mock_obter_reader):
        mock_reader = MagicMock()
        mock_obter_reader.return_value = mock_reader
        
        mock_reader.readtext.return_value = [
            ([[0, 0], [10, 0], [10, 10], [0, 10]], "Texto detectado sem confiança")
        ]
        mock_threshold.return_value = (None, None)
        
        vision = Vision()
        res = vision.extrair_texto_screenshot(caminho_imagem="dummy.png")
        self.assertEqual(res, "Texto detectado sem confiança")

    @patch('core.vision._obter_reader')
    def test_vision_extraction_failure_handling(self, mock_obter_reader):
        mock_obter_reader.side_effect = Exception("Falha catastrófica no motor de OCR")
        vision = Vision()
        res = vision.extrair_texto_screenshot(caminho_imagem="dummy.png")
        self.assertIn("FALHA NO DIAGNÓSTICO", res)
        self.assertIn("Falha catastrófica no motor de OCR", res)


class TestNetEyeCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = CacheManager(cache_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_memory_cache_get_set(self):
        self.cache.set("chave1", "valor1", ttl=10)
        self.assertEqual(self.cache.get("chave1"), "valor1")
        
        self.cache.set("chave2", "valor2", ttl=-1)
        self.assertIsNone(self.cache.get("chave2"))

    def test_comando_cache(self):
        cmd = "ajuda-me a navegar"
        resp = {"resposta": "ok"}
        self.cache.cache_comando(cmd, resp, ttl=5)
        self.assertEqual(self.cache.obter_comando_cache(cmd), resp)

    def test_url_index_persistence(self):
        self.cache.registar_url("https://exemplo.com", "Exemplo", {"meta": 1})
        visitada, info = self.cache.url_já_visitada("https://exemplo.com")
        self.assertTrue(visitada)
        self.assertEqual(info["titulo"], "Exemplo")
        self.assertEqual(info["metadata"]["meta"], 1)

    def test_cache_eviction_policy(self):
        # Forçar o limite superior a ser pequeno para testar a remoção
        self.cache.MAX_MEMORY_ENTRIES = 5
        
        for i in range(10):
            self.cache.set(f"key_{i}", f"val_{i}", ttl=10)
            time.sleep(0.001)
            
        # O tamanho deve ser limitado a MAX_MEMORY_ENTRIES
        self.assertEqual(len(self.cache._memory_cache), 5)
        # O key_0 deve ter sido removido por ser o mais antigo
        self.assertIsNone(self.cache.get("key_0"))


class TestNetEyeConnectionPool(unittest.TestCase):
    def test_pool_singleton(self):
        pool_1 = obter_pool()
        pool_2 = obter_pool()
        self.assertIs(pool_1, pool_2)

    @patch('core.connection_pool.create_client')
    def test_pool_connection_limits(self, mock_create_client):
        # Criar pool mockado
        mock_create_client.return_value = MagicMock()
        pool = SupabaseConnectionPool(min_size=1, max_size=3)
        
        # Pegar as 3 conexões
        c1 = pool.obter()
        c2 = pool.obter()
        c3 = pool.obter()
        
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        self.assertIsNotNone(c3)
        
        # A quarta tentativa deve bater no timeout e retornar None
        c4 = pool.obter(timeout=0.1)
        self.assertIsNone(c4)
        
        # Devolver uma e pegar de novo
        pool.devolver(c1)
        c4_retry = pool.obter(timeout=0.1)
        self.assertIs(c4_retry, c1)

    @patch('core.connection_pool.create_client')
    def test_pool_clean_up_and_closed_checkin(self, mock_create_client):
        mock_create_client.return_value = MagicMock()
        pool = SupabaseConnectionPool(min_size=2, max_size=2)
        
        c1 = pool.obter()
        pool.limpar()
        
        # Devolver após limpeza não deve reinserir conexão
        pool.devolver(c1)
        self.assertEqual(pool._active_count, 0)
        self.assertTrue(pool._pool.empty())


class TestNetEyeTranscriber(unittest.TestCase):
    def test_phonetic_corrections_exact_matches(self):
        # A transcrição deve aplicar corretamente os sinónimos fonéticos definidos
        with patch('core.transcriber._CORRECOES', {"io-tube": "youtube", "pode aceitar": "aceitar"}):
            self.assertEqual(_aplicar_correcoes("abre o io-tube"), "abre o youtube")
            self.assertEqual(_aplicar_correcoes("eu posso pode aceitar"), "eu posso aceitar")
            
            # Testar capitalização
            self.assertEqual(_aplicar_correcoes("Io-tube"), "Youtube")


class TestNetEyeBrowser(unittest.TestCase):
    def test_resolucao_url(self):
        br = BrowserController({"modo_headless": True})
        self.assertEqual(br._resolver_url("google"), "https://www.google.com")
        self.assertEqual(br._resolver_url("https://github.com"), "https://github.com")
        self.assertEqual(br._resolver_url("sapo.pt"), "https://sapo.pt")

    @patch('core.browser.sync_playwright')
    def test_persistent_context_launch_args(self, mock_playwright):
        # Testar se os argumentos e o viewport corretos são repassados ao context
        mock_pw_instance = MagicMock()
        mock_playwright.return_value.start.return_value = mock_pw_instance
        
        br = BrowserController({"modo_headless": True})
        br.iniciar()
        
        args, kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args
        
        self.assertTrue(kwargs["headless"])
        self.assertEqual(kwargs["viewport"], {"width": 1024, "height": 600})
        self.assertEqual(kwargs["locale"], "pt-PT")
        self.assertIn("--disable-blink-features=AutomationControlled", kwargs["args"])

    def test_timeout_adaptativo(self):
        br = BrowserController({"timeout_pagina": 8})
        br.iniciar = MagicMock()
        br.timeout = 8000
        self.assertEqual(br._obter_timeout_adaptativo("https://google.com"), 8000)
        self.assertEqual(br._obter_timeout_adaptativo("https://youtube.com/watch?v=123"), 15000)
        self.assertEqual(br._obter_timeout_adaptativo("https://instagram.com/p/123"), 15000)


if __name__ == "__main__":
    unittest.main()
