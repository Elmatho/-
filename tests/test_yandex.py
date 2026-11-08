import json
import unittest
from unittest.mock import patch, MagicMock
from bitrix_agents.yandex import YandexModel
from bitrix_agents.demo import history


class YandexTests(unittest.TestCase):
    def test_markdown_wrapped_json(self):
        # Модель иногда оборачивает корректный JSON в блок Markdown вопреки промпту.
        model = YandexModel('test', 'gpt://folder/yandexgpt/latest')
        payload = {'problem': 'Нет доступа', 'actions': [], 'sources': ['comment:1']}
        for prefix in ('```', '```json'):
            with self.subTest(prefix=prefix):
                with patch.object(model, 'complete', return_value=prefix + '\n' + json.dumps(payload) + '\n```'):
                    self.assertEqual(model.extract(history()), payload)

    def test_extra_prose_is_not_silently_discarded(self):
        model = YandexModel('test', 'gpt://folder/yandexgpt/latest')
        with patch.object(model, 'complete', return_value='Пояснение\n```json\n{}\n```'):
            with self.assertRaises(ValueError):
                model.extract(history())

    def test_missing_credentials(self):
        with self.assertRaises(ValueError):
            YandexModel('', '')

    @patch('bitrix_agents.yandex.urlopen')
    def test_request_and_response(self, request):
        response = MagicMock()
        response.read.return_value = json.dumps({'result': {'alternatives': [
            {'status': 'ALTERNATIVE_STATUS_FINAL', 'message': {'text': 'hello'}}]}}).encode()
        request.return_value.__enter__.return_value = response
        model = YandexModel('test-secret', 'gpt://folder/yandexgpt/latest')
        self.assertEqual(model.complete('system', 'question'), 'hello')
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(body['modelUri'], 'gpt://folder/yandexgpt/latest')
        self.assertEqual(request.call_args.kwargs['timeout'], 90)

    def test_invalid_extraction(self):
        model = YandexModel('test', 'gpt://folder/yandexgpt/latest')
        with patch.object(model, 'complete', return_value='{"problem": "x", "actions": "bad", "sources": []}'):
            with self.assertRaises(ValueError):
                model.extract(history())

    def test_repairs_invalid_extraction_once(self):
        model = YandexModel('test', 'gpt://folder/yandexgpt/latest')
        valid = {'problem':'Нет доступа','actions':[], 'sources':['comment:1']}
        with patch.object(model, 'complete', side_effect=['не JSON', json.dumps(valid)]) as call:
            self.assertEqual(model.extract(history()), valid)
        self.assertEqual(call.call_count, 2)

    @patch('bitrix_agents.yandex.urlopen', side_effect=TimeoutError('secret'))
    def test_safe_error(self, request):
        with self.assertRaisesRegex(RuntimeError, 'Yandex API') as error:
            YandexModel('test-secret', 'gpt://folder/yandexgpt/latest').complete('a', 'b')
        self.assertNotIn('secret', str(error.exception))
