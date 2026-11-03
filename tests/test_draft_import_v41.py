import os
import unittest
from unittest.mock import patch
from src import draft_import as di


def block(kind, value):
    return {'type': kind, kind: {'rich_text': [{'plain_text': value}]}}


def page():
    return {'id': 'page-1', 'properties': {
        '집필 요청 상태': {'select': {'name': 'PROMPT_READY'}}}}


class DraftImportTests(unittest.TestCase):
    def test_extract_draft_only_submission(self):
        blocks = [block('paragraph', 'old prompt'),
                  block('heading_2', '원고 제출'),
                  block('heading_2', '소제목'),
                  block('paragraph', '작성된 원고'),
                  block('heading_2', '자동 검수 결과'),
                  block('paragraph', 'old QA')]
        self.assertEqual(di.extract_draft(blocks), '## 소제목\n\n작성된 원고')

    def test_nested_list_import(self):
        parent = block('bulleted_list_item', '부모 항목')
        parent['id'] = 'nested-parent'
        parent['has_children'] = True
        children = [block('bulleted_list_item', '하위 항목'),
                    block('paragraph', '하위 설명')]
        with patch.object(di, 'get_blocks', return_value=children):
            draft = di.extract_draft([block('heading_2', '원고 제출'), parent])
        self.assertIn('부모 항목', draft)
        self.assertIn('하위 항목', draft)
        self.assertIn('하위 설명', draft)

    def test_nested_block_without_id_rejected(self):
        parent = block('bulleted_list_item', '항목')
        parent['has_children'] = True
        with self.assertRaisesRegex(ValueError, '하위 블록 ID 누락'):
            di.extract_draft([block('heading_2', '원고 제출'), parent])

    def test_notion_table_import(self):
        table = {'id': 'table-1', 'type': 'table',
                 'has_children': True, 'table': {'has_column_header': True}}
        def row(a, b):
            return {'type': 'table_row', 'table_row': {'cells': [
                [{'plain_text': a}], [{'plain_text': b}]]}}
        with patch.object(di, 'get_blocks', return_value=[
            row('항목', '설명'), row('음성 검색', '지원')]):
            result = di.extract_draft([block('heading_2', '원고 제출'), table])
        self.assertIn('| 항목 | 설명 |', result)
        self.assertIn('| --- | --- |', result)
        self.assertIn('| 음성 검색 | 지원 |', result)

    def test_table_without_id_rejected(self):
        with self.assertRaisesRegex(ValueError, '표 블록 ID 누락'):
            di.extract_draft([block('heading_2', '원고 제출'),
                              {'type': 'table', 'table': {}}])

    def test_empty_submission_waits(self):
        with patch.object(di, 'get_blocks', return_value=[block('paragraph', 'old prompt')]):
            self.assertEqual(di.process(page()), 'waiting')

    def test_short_draft_fails(self):
        result = di.qa('# 제목\n짧은 원고')
        self.assertFalse(result['passed'])
        self.assertTrue(result['errors'])

    def test_long_draft_passes_with_warning(self):
        result = di.qa('# 소제목\n' + '본문 내용입니다. ' * 85)
        self.assertTrue(result['passed'])
        self.assertIn('해시태그가 없음', result['warnings'])

    def test_placeholder_rejected(self):
        self.assertFalse(di.qa('# 제목\n' + '문장 ' * 150 + '[내용 입력]')['passed'])

    @patch('src.draft_import.main.notion')
    def test_import_saves_status_and_appends_report(self, notion):
        blocks = [block('heading_2', '원고 제출'),
                  block('paragraph', '# 소제목\n' + '본문 내용입니다. ' * 85)]
        with patch.object(di, 'get_blocks', return_value=blocks), patch.dict(os.environ, {'DRY_RUN': 'false'}):
            self.assertEqual(di.process(page()), 'imported')
        self.assertEqual(notion.call_count, 2)
        self.assertEqual(notion.call_args_list[0].args[:2], ('PATCH', '/blocks/page-1/children'))
        self.assertEqual(notion.call_args_list[1].kwargs['json']['properties']['집필 요청 상태']['select']['name'], 'DRAFT_IMPORTED')
        self.assertFalse(notion.call_args_list[1].kwargs['json']['properties']['검수 승인']['checkbox'])

    @patch('src.draft_import.main.notion')
    def test_dry_run_no_writes(self, notion):
        blocks = [block('heading_2', '원고 제출'),
                  block('paragraph', '# 제목\n' + '본문 내용입니다. ' * 85)]
        with patch.object(di, 'get_blocks', return_value=blocks), patch.dict(os.environ, {'DRY_RUN': 'true'}):
            self.assertEqual(di.process(page()), 'preview')
        notion.assert_not_called()

    def test_existing_report_is_not_duplicated(self):
        with patch.object(di, 'get_blocks', return_value=[block('heading_2', '자동 검수 결과')]), patch.dict(os.environ, {'DRY_RUN': 'true'}):
            self.assertEqual(di.process(page()), 'skipped')

    @patch('src.draft_import.main.notion')
    def test_recover_status_after_report_append(self, notion):
        blocks = [block('heading_2', '원고 제출'),
                  block('heading_2', '자동 검수 결과'),
                  block('paragraph', '검수 결과: 형식 검사 통과(사람 검수 필요)')]
        with patch.object(di, 'get_blocks', return_value=blocks), patch.dict(os.environ, {'DRY_RUN': 'false'}):
            self.assertEqual(di.process(page()), 'recovered')
        self.assertEqual(notion.call_count, 1)
        self.assertEqual(notion.call_args_list[0].args[:2], ('PATCH', '/pages/page-1'))
        self.assertEqual(notion.call_args_list[0].kwargs['json']['properties']['집필 요청 상태']['select']['name'], 'DRAFT_IMPORTED')

    @patch('src.draft_import.main.notion')
    def test_failed_qa_marks_review(self, notion):
        blocks = [block('heading_2', '원고 제출'), block('paragraph', '짧은 글')]
        with patch.object(di, 'get_blocks', return_value=blocks), patch.dict(os.environ, {'DRY_RUN': 'false'}):
            self.assertEqual(di.process(page()), 'needs_review')
        self.assertEqual(notion.call_args_list[-1].kwargs['json']['properties']['집필 요청 상태']['select']['name'], 'NEEDS_REVIEW')

    def test_pagination(self):
        with patch('src.draft_import.main.notion', side_effect=[
            {'results': [block('paragraph', 'one')], 'has_more': True, 'next_cursor': 'abc'},
            {'results': [block('paragraph', 'two')], 'has_more': False}]):
            self.assertEqual(len(di.get_blocks('id')), 2)

    def test_secrets_rejected(self):
        self.assertFalse(di.qa('본문 ' * 150 + ' sk-' + 'A'*30)['passed'])


if __name__ == '__main__':
    unittest.main()
