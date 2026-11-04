import os
import unittest
from unittest.mock import patch
from src import prompt_packet as pp


def candidate(state='선택', rating='안전', linked=False):
    return {'id': 'recommend-1', 'properties': {
        '상태': {'select': {'name': state}},
        '연결 글': {'relation': [{'id': 'content-1'}] if linked else []},
        '논란도': {'select': {'name': rating}},
        '신빙성': {'select': {'name': '안전'}},
        '불쾌도': {'select': {'name': '안전'}},
        '근거 출처': {'relation': [{'id': 'source-1'}]},
        '분야': {'select': {'name': '일상'}},
        '후보 제목': {'title': [{'plain_text': '가을 산책'}]},
        '한 줄 요약': {'rich_text': [{'plain_text': '산책 습관'}]},
    }}


class V39Tests(unittest.TestCase):
    def test_only_selected_approved_unlinked(self):
        self.assertTrue(pp.eligible(candidate())[0])
        self.assertFalse(pp.eligible(candidate(state='보류'))[0])
        self.assertTrue(pp.eligible(candidate(rating='주의'))[0])
        self.assertFalse(pp.eligible(candidate(linked=True))[0])

    @patch('src.prompt_packet.main.notion')
    def test_unverified_source_allowed_after_human_approval(self, notion):
        notion.return_value = {'properties': {'검증 상태': {'select': {'name': '미검증'}}, 'URL': {'url': 'https://example.org'}}}
        self.assertEqual(pp.source_details(candidate())[0][1], 'https://example.org')

    @patch('src.prompt_packet.main.notion')
    def test_missing_source_url_rejected(self, notion):
        notion.return_value = {'properties': {'검증 상태': {'select': {'name': '검증 완료'}}, 'URL': {'url': None}}}
        with self.assertRaisesRegex(ValueError, '유효한 출처 URL 없음'):
            pp.source_details(candidate())

    @patch('src.prompt_packet.main.notion')
    @patch('src.prompt_packet.main.query')
    def test_create_and_repeated_run_no_duplicate(self, query, notion):
        page = candidate()
        query.return_value = []
        notion.side_effect = [
            {'properties': {'검증 상태': {'select': {'name': '검증 완료'}}, 'URL': {'url': 'https://example.org'}, '자료명': {'title': [{'plain_text': '검증 자료'}]}}},
            {'id': 'new-content'},
            {},
        ]
        with patch.dict(os.environ, {'DRY_RUN': 'false'}):
            self.assertEqual(pp.process(page), 'created')
        create = [call for call in notion.call_args_list if call.args[:2] == ('POST', '/pages')]
        self.assertEqual(len(create), 1)
        properties = create[0].kwargs['json']['properties']
        self.assertEqual(properties['이미지 프롬프트 수']['number'], 3)
        self.assertEqual(properties['집필 요청 상태']['select']['name'], '집필 준비 완료')
        self.assertEqual(properties['집필 방식']['select']['name'], 'ChatGPT 프로젝트')
        self.assertFalse(properties['검수 승인']['checkbox'])
        self.assertFalse(pp.eligible(candidate(linked=True))[0])

    @patch('src.prompt_packet.main.notion')
    @patch('src.prompt_packet.main.query')
    def test_recover_existing_content(self, query, notion):
        query.return_value = [{'id': 'already-exists'}]
        notion.return_value = {'properties': {'검증 상태': {'select': {'name': '검증 완료'}}, 'URL': {'url': 'https://example.org'}, '자료명': {'title': [{'plain_text': '검증 자료'}]}}}
        with patch.dict(os.environ, {'DRY_RUN': 'false'}):
            self.assertEqual(pp.process(candidate()), 'recovered')
        self.assertFalse(any(c.args[:2] == ('POST', '/pages') for c in notion.call_args_list))

    @patch('src.prompt_packet.main.notion')
    def test_dry_run_no_writes(self, notion):
        notion.return_value = {'properties': {'검증 상태': {'select': {'name': '검증 완료'}}, 'URL': {'url': 'https://example.org'}, '자료명': {'title': [{'plain_text': '검증 자료'}]}}}
        with patch.dict(os.environ, {'DRY_RUN': 'true'}):
            self.assertEqual(pp.process(candidate()), 'preview')
        self.assertTrue(all(c.args[0] == 'GET' for c in notion.call_args_list))

    def test_image_prompts(self):
        images = pp.image_prompts('가을 산책', '일상')
        self.assertEqual(len(images), 3)
        self.assertIn('16:9', images[0][1])
        self.assertTrue(all('4:3' in x[1] for x in images[1:]))


if __name__ == '__main__':
    unittest.main()
