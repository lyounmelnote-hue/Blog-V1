import os
import unittest
from unittest.mock import patch
from src import score_backfill as bf


def rich(text):
    return [{'plain_text': text}]


def row(ident='a', score=None, note='기존 검증 메모'):
    return {'id': ident, 'properties': {
        '후보 제목': {'title': [{'plain_text': '생활 정보 신청 방법'}]},
        '한 줄 요약': {'rich_text': rich('신청 방법을 확인하세요')},
        '원본 링크': {'url': 'https://example.com'},
        '추천 점수': {'number': score},
        '검증 메모': {'rich_text': rich(note)},
        '상태': {'select': {'name': '선택'}},
        '연결 글': {'relation': [{'id': 'linked-content'}]},
    }}


class ScoreBackfillTests(unittest.TestCase):
    def test_pending_missing_score(self):
        self.assertTrue(bf.eligible(row()))
        self.assertFalse(bf.eligible(row(score=65)))
        self.assertTrue(bf.eligible(row(score=65), force=True))

    def test_existing_backfill_mark_skipped(self):
        self.assertFalse(bf.eligible(row(note=bf.PREFIX + '완료')))

    def test_calculation_is_bounded(self):
        results = bf.calculate([row()], lookup=lambda _: 3000)
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0][1]['total'], 0)
        self.assertLessEqual(results[0][1]['total'], 100)

    def test_payload_preserves_approval_and_links(self):
        candidate = row()
        result = bf.calculate([candidate], lookup=lambda _: 10)[0][1]
        payload = bf.patch_payload(candidate, result)
        self.assertEqual(set(payload['properties']), {'추천 점수', '검증 메모'})
        self.assertIn('기존 검증 메모', payload['properties']['검증 메모']['rich_text'][0]['text']['content'])

    def test_long_note_fails_closed(self):
        candidate = row(note='메모' * 1000)
        result = bf.calculate([candidate], lookup=lambda _: 10)[0][1]
        with self.assertRaisesRegex(ValueError, '길이 초과'):
            bf.patch_payload(candidate, result)

    @patch('src.score_backfill.notion')
    @patch('src.score_backfill.daily.existing_day_rows')
    @patch('src.score_backfill.daily.blog_result_count', return_value=200)
    def test_dry_run_never_patches(self, lookup, get_rows, notion):
        get_rows.return_value = [row()]
        with patch.dict(os.environ, {'BACKFILL_DATE':'2026-11-03','DRY_RUN':'true'}):
            bf.run()
        notion.assert_not_called()

    @patch('src.score_backfill.notion')
    @patch('src.score_backfill.daily.existing_day_rows')
    @patch('src.score_backfill.daily.blog_result_count', return_value=200)
    def test_real_run_updates_only_two_properties(self, lookup, get_rows, notion):
        get_rows.return_value = [row()]
        with patch.dict(os.environ, {'BACKFILL_DATE':'2026-11-03','DRY_RUN':'false'}):
            bf.run()
        self.assertEqual(notion.call_args.args[:2], ('PATCH', '/pages/a'))
        self.assertEqual(set(notion.call_args.kwargs['json']['properties']), {'추천 점수','검증 메모'})

    @patch('src.score_backfill.notion')
    @patch('src.score_backfill.daily.existing_day_rows')
    def test_idempotent_existing_score(self, get_rows, notion):
        get_rows.return_value = [row(score=73)]
        with patch.dict(os.environ, {'BACKFILL_DATE':'2026-11-03','DRY_RUN':'false'}):
            bf.run()
        notion.assert_not_called()

    def test_missing_date_rejected(self):
        with patch.dict(os.environ, {'BACKFILL_DATE':''}):
            with self.assertRaisesRegex(ValueError, '필수'):
                bf.run()


if __name__ == '__main__':
    unittest.main()
