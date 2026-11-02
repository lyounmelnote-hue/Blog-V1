import os
import unittest
from unittest.mock import patch
from src import main

class PipelineTests(unittest.TestCase):
    def test_chunking_does_not_truncate(self):
        result = main.blocks('a' * 4001)
        self.assertEqual(len(result), 3)
        self.assertEqual(''.join(b[b['type']]['rich_text'][0]['text']['content'] for b in result), 'a' * 4001)

    def test_too_many_blocks_rejected(self):
        with self.assertRaises(ValueError):
            main.blocks('a\n' * 101)

    def test_textprop(self):
        self.assertEqual(main.textprop({'properties': {'키워드': {'title': [{'plain_text': '테스트'}]}}}, '키워드'), '테스트')

    @patch.object(main, 'content_for_keyword')
    @patch.object(main, 'keyword_state')
    def test_duplicate_reconciles(self, state, content):
        content.return_value = [{'id': 'content-1'}]
        with patch.object(main, 'save_log'):
            self.assertTrue(main.reconcile('keyword-1', 'run-1', dry=False))
        state.assert_called_once_with('keyword-1', 'DONE')

    @patch.object(main, 'content_for_keyword')
    @patch.object(main, 'keyword_state')
    def test_dry_run_no_state_mutation(self, state, content):
        content.return_value = [{'id': 'content-1'}]
        self.assertTrue(main.reconcile('keyword-1', 'run-1', dry=True))
        state.assert_not_called()

    @patch.object(main, 'notion')
    def test_draft_creation_not_retried(self, notion):
        with patch.dict(os.environ, {'OPENAI_MODEL': 'test'}):
            main.save_draft('kw-1', {'title': '제목', 'body': '본문'}, 'run-1')
        self.assertFalse(notion.call_args.kwargs['safe_retry'])
        self.assertEqual(notion.call_args.kwargs['json']['properties']['상태']['select']['name'], 'REVIEW')

if __name__ == '__main__':
    unittest.main()
