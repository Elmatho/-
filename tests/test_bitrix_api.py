import unittest
from unittest.mock import patch, MagicMock
from bitrix_agents.bitrix_api import BitrixReader


class BitrixReaderTests(unittest.TestCase):
    def test_only_https_webhook(self):
        with self.assertRaises(ValueError):
            BitrixReader('http://example.test/rest/1/secret/')

    @patch('bitrix_agents.bitrix_api.urlopen')
    def test_read_task_and_chat(self, opener):
        responses = [
            {'result': {'task': {'id': '10', 'title': 'Тест', 'description': 'Описание',
                                 'groupId': '3', 'chatId': 7, 'status': '5'}}},
            {'result': {'messages': [{'id': 91, 'author_id': 4, 'date': '2025-01-01',
                                     'text': 'Сделано'}]}}]
        def fake(req, timeout):
            response = MagicMock()
            response.read.return_value = __import__('json').dumps(responses.pop(0)).encode()
            response.__enter__.return_value = response
            return response
        opener.side_effect = fake
        reader = BitrixReader('https://example.test/rest/1/secret/')
        item = reader.read_task(10)
        self.assertEqual(item['comments'][0]['id'], '91')
        self.assertEqual(item['scope'], 'example.test/3')
        self.assertEqual(len(opener.call_args_list), 2)

    @patch('bitrix_agents.bitrix_api.urlopen')
    def test_missing_chat_fails_closed(self, opener):
        response = MagicMock()
        response.read.return_value = b'{"result":{"task":{"id":"10","title":"T"}}}'
        opener.return_value.__enter__.return_value = response
        with self.assertRaisesRegex(RuntimeError, 'чат'):
            BitrixReader('https://example.test/rest/1/secret/').read_task(10)
