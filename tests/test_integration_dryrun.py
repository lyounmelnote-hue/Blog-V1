import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from src import daily, integration_dryrun as integration


def row(title, url, category='문화', slot=1):
    return {'id': 'prior', 'properties': {
        '후보 제목': {'title': [{'plain_text': title}]},
        '원본 링크': {'url': url}, '분야': {'select': {'name': category}},
        '슬롯 번호': {'number': slot}}}


class ReadOnlyIntegrationTests(unittest.TestCase):
    def test_live_pipeline_with_mocked_http(self):
        queries = []
        def transport(session, method, url, **kwargs):
            response = requests.Response()
            response.status_code = 200
            if 'api.notion.com' in url:
                filters = kwargs['json']['filter']
                queries.append(filters)
                rows = ([row('기존 추천 문화', 'https://example.com/existing'),
                         row('기존 추천 일상', 'https://example.com/existing2', '일상', 2)]
                        if 'property' in filters else
                        [row('과거 소재 세부 안내', 'https://example.com/history')])
                data = {'results': rows, 'has_more': False}
            elif kwargs['params']['display'] == 1:
                data = {'total': 100}
            else:
                from urllib.parse import quote
                query = kwargs['params']['query']
                endpoint = url.split('/')[-1]
                title = query + ' ' + endpoint + ' 설치 비교'
                link = 'https://example.com/' + quote(query) + '/' + endpoint
                lead = {'title': title, 'description': '신청 방법 및 준비물 안내', 'link': link}
                data = {'items': [
                    {'title': '과거 소재 세부 안내', 'description': '이전 소재', 'link': 'https://example.com/history?utm_source=test'},
                    lead, dict(lead),
                    {'title': '선거 정치인 뉴스', 'description': '위험 주제', 'link': link + '/unsafe'}]}
            response._content = json.dumps(data).encode('utf-8')
            return response
        credentials = {'DRY_RUN': 'true', 'REVIEW_QUEUE': 'true', 'RECOMMEND_DATE': '2026-11-05',
                       'NOTION_TOKEN': 'fixture', 'NAVER_CLIENT_ID': 'fixture',
                       'NAVER_CLIENT_SECRET': 'fixture', 'GITHUB_STEP_SUMMARY': ''}
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.dict(os.environ, credentials), \
                     patch.object(requests.sessions.Session, 'request', transport), \
                     patch.object(daily, 'save_log') as log, \
                     patch.object(daily, 'save_candidate') as save, \
                     patch.object(daily, 'save_review_candidate') as queue, \
                     patch.object(daily, 'create_unverified_source') as source, \
                     contextlib.redirect_stdout(io.StringIO()):
                    report = integration.run()
                for writer in (log, save, queue, source):
                    writer.assert_not_called()
                self.assertEqual(report['summary']['selected'], 8)
                self.assertEqual(report['forbidden_requests'], 0)
                self.assertTrue(all(x['duplicates'] > 0 for x in report['collection']))
                self.assertTrue(any(x['rejected'] for x in report['collection']))
                self.assertGreater(report['http_calls']['news.json'], 0)
                self.assertGreater(report['http_calls']['blog.json'], 0)
                self.assertEqual(queries[1]['and'], [
                    {'property': '추천일', 'date': {'on_or_after': '2026-10-29'}},
                    {'property': '추천일', 'date': {'before': '2026-11-05'}}])
                self.assertTrue(Path('integration-report/summary.json').is_file())
            finally:
                os.chdir(previous)

    def test_forbidden_http_never_reaches_transport(self):
        from unittest.mock import Mock
        transport = Mock()
        guard = integration.ReadOnlyTransport(transport)
        for method, url in [('POST', 'https://api.notion.com/v1/pages'),
                            ('PATCH', 'https://api.notion.com/v1/pages/id'),
                            ('DELETE', 'https://api.notion.com/v1/blocks/id'),
                            ('POST', 'https://other.example/query'),
                            ('POST', 'https://api.notion.com/v1/data_sources/other/query')]:
            with self.assertRaises(integration.ReadOnlyViolation):
                guard.request(None, method, url)
        transport.assert_not_called()
        self.assertEqual(guard.blocked, 5)

    def test_bad_modes_fail_before_network(self):
        for dry, queue in [('false', 'true'), ('true', 'false')]:
            with patch.dict(os.environ, {'DRY_RUN': dry, 'REVIEW_QUEUE': queue}), \
                 patch.object(requests.sessions.Session, 'request') as network:
                with self.assertRaises(RuntimeError):
                    integration.run()
                network.assert_not_called()

    def test_redirects_are_not_followed(self):
        from unittest.mock import Mock
        response = requests.Response()
        response.status_code = 307
        transport = Mock(return_value=response)
        guard = integration.ReadOnlyTransport(transport)
        with self.assertRaises(integration.ReadOnlyViolation):
            guard.request(None, 'GET', 'https://openapi.naver.com/v1/search/news.json')
        self.assertFalse(transport.call_args.kwargs['allow_redirects'])


if __name__ == '__main__':
    unittest.main()
