"""Read-only integration harness. Production entry points remain unchanged."""
import contextlib
import io
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

import requests
from . import daily


class ReadOnlyViolation(RuntimeError):
    pass


class ReadOnlyTransport:
    def __init__(self, transport):
        self.transport = transport
        self.calls = Counter()
        self.blocked = 0

    def request(self, session, method, url, **kwargs):
        parsed = urlparse(url)
        method = method.upper()
        notion_query = (parsed.hostname == 'api.notion.com' and method == 'POST'
                        and parsed.path == '/v1/data_sources/' + daily.DAILY + '/query')
        naver_query = (parsed.hostname == 'openapi.naver.com' and method == 'GET'
                       and parsed.path in ('/v1/search/news.json', '/v1/search/blog.json'))
        if parsed.scheme != 'https' or not (notion_query or naver_query):
            self.blocked += 1
            raise ReadOnlyViolation('Integration permits only Notion data-source queries and Naver searches')
        self.calls['notion_query' if notion_query else parsed.path.rsplit('/', 1)[-1]] += 1
        kwargs['allow_redirects'] = False
        response = self.transport(session, method, url, **kwargs)
        if 300 <= response.status_code < 400:
            self.blocked += 1
            raise ReadOnlyViolation('Redirect refused by read-only integration transport')
        return response


def run():
    if os.getenv('DRY_RUN') != 'true' or os.getenv('REVIEW_QUEUE') != 'true':
        raise RuntimeError('Integration requires DRY_RUN=true and REVIEW_QUEUE=true')
    missing = [key for key in ('NOTION_TOKEN', 'NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET')
               if not os.getenv(key)]
    if missing:
        raise RuntimeError('Missing required credentials: ' + ', '.join(missing))
    guard = ReadOnlyTransport(requests.sessions.Session.request)
    output = io.StringIO()
    def guarded(session, method, url, **kwargs):
        return guard.request(session, method, url, **kwargs)
    try:
        with patch.object(requests.sessions.Session, 'request', guarded), contextlib.redirect_stdout(output):
            daily.run()
    finally:
        print(output.getvalue(), end='')
        print('READ_ONLY_TRANSPORT', json.dumps({'calls': dict(guard.calls), 'blocked': guard.blocked}))
    if guard.blocked:
        raise ReadOnlyViolation('A forbidden request was attempted, even if the caller caught it')
    records = {}
    for line in output.getvalue().splitlines():
        tag, _, payload = line.partition(' ')
        if tag in ('COLLECT_DIAGNOSTICS', 'DEDUP_DIAGNOSTICS', 'FLEXIBLE_ALLOCATION', 'RUN_SUMMARY', 'QUALITY_REPORT',
                   'RECOMMENDATION', 'CANDIDATE_REJECTED', 'TOPIC_DEDUP', 'SEARCH_API_DIAGNOSTICS'):
            records.setdefault(tag, []).append(json.loads(payload))
    existing = records['DEDUP_DIAGNOSTICS'][0]['existing_rows']
    if existing >= 10:
        raise RuntimeError('Date already full; live collection was skipped. Choose a date with free slots.')
    collected = records.get('COLLECT_DIAGNOSTICS', [])
    summary = records['RUN_SUMMARY'][0]
    allocation = records['FLEXIBLE_ALLOCATION'][0]
    if len(collected) != len(daily.CATEGORIES) or sum(x['raw'] for x in collected) == 0:
        raise RuntimeError('Live source collection produced no usable diagnostic evidence')
    if not 0 <= summary['selected'] <= max(0, 10 - existing):
        raise AssertionError('Daily capacity exceeded')
    if summary['selected'] != allocation['selected']:
        raise AssertionError('Allocation and summary disagree')
    quality = records['QUALITY_REPORT'][0]
    if quality['selected'] != summary['selected'] or quality['unfilled'] != allocation['remaining_unfilled']:
        raise AssertionError('Quality report and final allocation disagree')
    if sum(quality['raw_by_endpoint'].values()) != sum(x['raw'] for x in collected):
        raise AssertionError('Endpoint totals and collected candidates disagree')
    if any(endpoint not in quality['raw_by_endpoint'] for endpoint in ('news', 'blog')):
        raise AssertionError('Both news and blog source collection are required')
    if sum(int(n) for n in quality['score_distribution'].values()) != summary['selected']:
        raise AssertionError('Quality score distribution does not match selected count')
    if any(int(score) < daily.MIN_EDITORIAL_SCORE for score in quality['score_distribution']):
        raise AssertionError('Below-threshold candidate was selected')
    report = {'status': 'passed', 'summary': summary, 'allocation': allocation, 'quality': quality,
              'recommendations': records.get('RECOMMENDATION', []),
              'excluded': records.get('CANDIDATE_REJECTED', []) + records.get('TOPIC_DEDUP', []),
              'search_api': records.get('SEARCH_API_DIAGNOSTICS', []),
              'collection': collected, 'http_calls': dict(guard.calls),
              'forbidden_requests': guard.blocked,
              'note': 'Search results are unverified leads; result totals are not search volume.'}
    report_dir = Path('integration-report')
    report_dir.mkdir(exist_ok=True)
    (report_dir / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('INTEGRATION_VALIDATED', json.dumps(report, ensure_ascii=False))
    summary_path = os.getenv('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a', encoding='utf-8') as handle:
            handle.write('### v4.5.2 read-only integration\n\n```json\n' + json.dumps(report, ensure_ascii=False, indent=2) + '\n```\n')
    return report


if __name__ == '__main__':
    run()
