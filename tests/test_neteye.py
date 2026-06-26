import os
import sys
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
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# Adicionar raiz ao path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Configurar variáveis de ambiente mock para testes
os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
os.environ["SUPABASE_KEY"] = "mock-key-123"
os.environ["NETEYE_ENCRYPTION_KEY"] = "mock-encryption-key-12345678"

from core.database import Database
from core.listener import Listener
from core.eleven_speaker import ElevenSpeaker
from core.talker import Talker
from core.assistant import Assistant
from core.vision import Vision
from core.cache_manager import CacheManager

class TestNetEyeDatabase(unittest.TestCase):
    @patch('core.database.create_client')
    def test_encryption_decryption(self, mock_create_client):
        # Configurar mock do cliente Supabase
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        # Simular o retorno da tabela configuracoes
        # Para api_key, vamos retornar uma chave criptografada
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
    def test_guardar_configuracao_api_key(self, mock_create_client):
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        db = Database()
        db.client = mock_client
        
        # Mock para table("configuracoes").upsert().execute()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        
        # Ao guardar api_key, o valor deve ser criptografado antes do upsert
        db.guardar_configuracao(1, "api_key", "sk-ant-mykey")
        args, kwargs = mock_table.upsert.call_args
        data = args[0]
        self.assertTrue(data["valor"].startswith("gAAAAA"))
        self.assertEqual(data["chave"], "api_key")
        
        # Ao guardar outra config (ex: volume), não encripta
        db.guardar_configuracao(1, "volume", "80")
        args, kwargs = mock_table.upsert.call_args
        data = args[0]
        self.assertEqual(data["valor"], "80")


class TestNetEyeListener(unittest.TestCase):
    def test_get_vad_bytes_normalization(self):
        # Config padrão do listener
        config = {
            "aggressividade": 2,
            "silencio_para_processar": 0.8,
            "tempo_minimo_fala": 0.3,
            "usar_wake_word": False
        }
        
        listener = Listener(config)
        expected_len = listener.frame_size * 2 # 480 * 2 = 960 bytes
        
        # Caso 1: Frame mais curto
        short_frame = np.zeros(300, dtype=np.int16)
        res_bytes = listener._get_vad_bytes(short_frame)
        self.assertEqual(len(res_bytes), expected_len)
        
        # Caso 2: Frame mais longo
        long_frame = np.zeros(600, dtype=np.int16)
        res_bytes = listener._get_vad_bytes(long_frame)
        self.assertEqual(len(res_bytes), expected_len)
        
        # Caso 3: Frame exato
        exact_frame = np.zeros(480, dtype=np.int16)
        res_bytes = listener._get_vad_bytes(exact_frame)
        self.assertEqual(len(res_bytes), expected_len)


class TestNetEyeSpeaker(unittest.TestCase):
    @patch('core.eleven_speaker.ElevenLabs')
    def test_volume_speed_limits(self, mock_elevenlabs):
        config = {
            "rate": 160,
            "volume": 1.0,
            "idioma": "pt-PT"
        }
        speaker = ElevenSpeaker(config)
        
        # Volume deve respeitar limites (0.0 a 2.0)
        speaker.ajustar_volume(0.5) # 1.5
        self.assertAlmostEqual(speaker.volume, 1.5)
        
        speaker.ajustar_volume(1.0) # 2.5 -> limita a 2.0
        self.assertAlmostEqual(speaker.volume, 2.0)
        
        speaker.ajustar_volume(-3.0) # -> limita a 0.0
        self.assertAlmostEqual(speaker.volume, 0.0)
        
        # Velocidade deve respeitar limites (50 a 400)
        speaker.ajustar_velocidade(50) # 210
        self.assertEqual(speaker.rate, 210)
        
        speaker.ajustar_velocidade(300) # 510 -> limita a 400
        self.assertEqual(speaker.rate, 400)
        
        speaker.ajustar_velocidade(-500) # -> limita a 50
        self.assertEqual(speaker.rate, 50)


class TestNetEyeTalker(unittest.TestCase):
    def test_talker_silent_under_2s_on_default(self):
        falar_mock = MagicMock()
        talker = Talker(falar_mock)
        
        # Iniciar comando "default" e parar logo em seguida
        talker.iniciar_comando("default")
        talker.parar()
        
        # Não deve ter falado nada (porque parou antes de 2 segundos)
        falar_mock.assert_not_called()

    def test_talker_immediate_cues_on_tool(self):
        falar_mock = MagicMock()
        talker = Talker(falar_mock)
        
        talker.iniciar_comando("navegar")
        # Deve ter falado imediatamente (sem esperar)
        import time
        time.sleep(0.1)
        talker.parar()
        
        falar_mock.assert_called()


class TestNetEyeAssistant(unittest.TestCase):
    @patch('anthropic.Anthropic')
    def test_multi_tool_execution(self, mock_anthropic):
        # Configurar mocks para o cliente Claude
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        # Simular uma chamada com múltiplas ferramentas
        mock_msg = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        
        # Blocos de conteúdo retornados pelo Claude
        class MockText:
            type = "text"
            text = "Vou preencher o campo e submeter."
        class MockToolUse:
            def __init__(self, id, name, input):
                self.id = id
                self.type = "tool_use"
                self.name = name
                self.input = input
        
        # Retorna duas chamadas consecutivas de ferramenta na mesma resposta
        mock_msg.content = [
            MockText(),
            MockToolUse("tool-1", "escrever", {"texto": "ajuda"}),
            MockToolUse("tool-2", "pressionar_enter", {})
        ]
        
        assistant = Assistant({"assistente": {"talker_ativo": False}}, api_key="sk-ant-test")
        assistant.client = mock_client
        
        # Mapear callbacks das ferramentas
        tool1_cb = MagicMock(return_value={"ok": True})
        tool2_cb = MagicMock(return_value={"ok": True})
        
        assistant.registar_ferramenta("escrever", tool1_cb)
        assistant.registar_ferramenta("pressionar_enter", tool2_cb)
        
        falar_mock = MagicMock()
        assistant.registar_falar(falar_mock)
        
        # Processar comando (Claude vai disparar as ferramentas e depois saímos por exaustão ou limite)
        # Vamos rodar _loop_claude. Ele deve executar AMBAS as ferramentas na mesma iteração.
        # Para simular o final, na segunda iteração o Claude retorna apenas texto.
        mock_msg_final = MagicMock()
        mock_msg_final.content = [MockText()]
        mock_client.messages.create.side_effect = [mock_msg, mock_msg_final]
        
        history = [{"role": "user", "content": "escreve ajuda"}]
        assistant._loop_claude(history, user_id=1)
        
        # Ambas as ferramentas devem ter sido executadas!
        tool1_cb.assert_called_once_with(texto="ajuda")
        tool2_cb.assert_called_once()
        
        # E o histórico deve conter os resultados agregados
        self.assertEqual(len(history), 3) # original, assistant (com tool_uses), user (com tool_results)
        self.assertEqual(history[2]["role"], "user")
        self.assertEqual(len(history[2]["content"]), 2) # Ambos os resultados de ferramentas
        self.assertEqual(history[2]["content"][0]["tool_use_id"], "tool-1")
        self.assertEqual(history[2]["content"][1]["tool_use_id"], "tool-2")


class TestNetEyeVision(unittest.TestCase):
    @patch('core.vision._obter_reader')
    @patch('cv2.imread')
    @patch('cv2.cvtColor')
    @patch('cv2.threshold')
    @patch('cv2.imwrite')
    def test_vision_extraction_mocked(self, mock_imwrite, mock_threshold, mock_cvtColor, mock_imread, mock_obter_reader):
        mock_reader = MagicMock()
        mock_obter_reader.return_value = mock_reader
        
        # Mock OCR result
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


class TestNetEyeCache(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = CacheManager(cache_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_memory_cache_get_set(self):
        # Valor normal
        self.cache.set("chave1", "valor1", ttl=10)
        self.assertEqual(self.cache.get("chave1"), "valor1")
        
        # Valor expirado
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


if __name__ == "__main__":
    unittest.main()
