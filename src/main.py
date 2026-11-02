"""Notion-driven draft pipeline v3.0. No publishing, no unverified citations."""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

BASE = 'https://api.notion.com/v1'
VERSION = '2025-09-03'
KEYWORDS = os.getenv('NOTION_KEYWORDS_DS', '2160808c-8a50-46c2-b9c1-39059218d701')
CONTENT = os.getenv('NOTION_CONTENT_DS', 'b2ace958-aa15-4105-973b-5fb1af090ec3')
SOURCES = os.getenv('NOTION_SOURCES_DS', '51596cf1-d049-472d-9689-8048f527ab41')
LOGS = os.getenv('NOTION_LOGS_DS', '25735bf7-9a91-4d0a-a596-d867d9c66447')


def request(method, url, *, headers=None, safe_retry=True, **kwargs):
    """Retry read/idempotent requests only; never blindly retry page creation."""
    tries = 4 if safe_retry else 1
    for attempt in range(tries):
        try:
            response = requests.request(method, url, headers=headers, timeout=(10, 45), **kwargs)
            if safe_retry and response.status_code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                wait = response.headers.get('Retry-After')
                try:
                    delay = min(max(float(wait), 0), 20) if wait else 2 ** attempt
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError('retry exhausted')


def notion(method, path, *, safe_retry=True, **kwargs):
    return request(method, BASE + path, safe_retry=safe_retry, headers={
        'Authorization': 'Bearer ' + os.environ['NOTION_TOKEN'],
        'Notion-Version': VERSION, 'Content-Type': 'application/json'}, **kwargs)


def query(ds, filter_=None, page_size=50, max_pages=20):
    result, cursor = [], None
    for _ in range(max_pages):
        payload = {'page_size': min(page_size, 100)}
        if filter_:
            payload['filter'] = filter_
        if cursor:
            payload['start_cursor'] = cursor
        data = notion('POST', f'/data_sources/{ds}/query', json=payload)
        result.extend(data.get('results', []))
        if not data.get('has_more'):
            return result
        cursor = data.get('next_cursor')
        if not cursor:
            raise RuntimeError('Notion pagination cursor missing')
    raise RuntimeError('Notion query pagination limit exceeded; narrow the filter')


def textprop(page, name):
    prop = page.get('properties', {}).get(name, {})
    return ''.join(v.get('plain_text', v.get('text', {}).get('content', ''))
                   for v in (prop.get('title') or prop.get('rich_text') or []))


def rich(value):
    return [{'type': 'text', 'text': {'content': str(value)[i:i + 1800]}}
            for i in range(0, len(str(value)), 1800)] or []


def blocks(value):
    output = []
    for line in value.splitlines():
        if not line.strip():
            continue
        kind = 'heading_2' if line.startswith('## ') else 'paragraph'
        line = line[3:] if kind == 'heading_2' else line
        for i in range(0, len(line), 1800):
            block_kind = kind if i == 0 else 'paragraph'
            output.append({'object': 'block', 'type': block_kind,
                           block_kind: {'rich_text': rich(line[i:i + 1800])}})
    if len(output) > 100:
        raise ValueError('Draft exceeds Notion initial 100-block limit; refusing to truncate')
    return output


def keyword_state(page_id, state):
    return notion('PATCH', f'/pages/{page_id}', json={
        'properties': {'상태': {'select': {'name': state}}}})


def keyword_page(page_id):
    return notion('GET', f'/pages/{page_id}')


def content_for_keyword(page_id):
    return query(CONTENT, {'property': '키워드', 'relation': {'contains': page_id}}, page_size=20)


def save_log(name, run_id, stage, result, message='', content_id=None):
    if os.getenv('DRY_RUN', 'true').lower() == 'true':
        return
    props = {
        '로그명': {'title': rich(name[:150])},
        '실행 ID': {'rich_text': rich(run_id)},
        '단계': {'select': {'name': stage}},
        '결과': {'select': {'name': result}},
        '오류 메시지': {'rich_text': rich(message[:1800])},
        '실행시각': {'date': {'start': datetime.now(timezone.utc).isoformat()}}}
    if content_id:
        props['대상 콘텐츠'] = {'relation': [{'id': content_id}]}
    try:
        notion('POST', '/pages', safe_retry=False, json={
            'parent': {'type': 'data_source_id', 'data_source_id': LOGS}, 'properties': props})
    except Exception as error:
        print('WARNING: Notion logging failed:', type(error).__name__, file=sys.stderr)


def naver_search(keyword):
    data = request('GET', 'https://openapi.naver.com/v1/search/blog.json', headers={
        'X-Naver-Client-Id': os.environ['NAVER_CLIENT_ID'],
        'X-Naver-Client-Secret': os.environ['NAVER_CLIENT_SECRET']},
        params={'query': keyword, 'display': 10, 'sort': 'sim'})
    return [{'title': re.sub(r'<[^>]+>', '', html.unescape(x.get('title', ''))),
             'description': re.sub(r'<[^>]+>', '', html.unescape(x.get('description', ''))),
             'url': x.get('link', '')} for x in data.get('items', [])]


def verified_sources():
    rows = query(SOURCES, {'property': '검증 상태', 'select': {'equals': 'VERIFIED'}}, 100)
    sources = []
    for page in rows:
        prop = page.get('properties', {})
        url = prop.get('URL', {}).get('url')
        if url:
            sources.append({'title': textprop(page, '자료명'), 'url': url,
                            'evidence': textprop(page, '주요 근거')})
    return sources[:30]


def generate(*args, **kwargs):
    """Legacy API writer intentionally disabled in v3.4."""
    raise RuntimeError('API 집필은 v3.4에서 비활성화됨. ChatGPT 프로젝트 프롬프트를 사용하세요.')


def save_draft(keyword_id, draft, run_id):
    body = draft['body'] + '\n\n## 사람 검수 필수\n공식 근거, 최신성, 저작권, 링크를 확인한 뒤 수동 게시하세요.'
    return notion('POST', '/pages', safe_retry=False, json={
        'parent': {'type': 'data_source_id', 'data_source_id': CONTENT},
        'properties': {
            '제목': {'title': rich(draft['title'][:150])},
            '키워드': {'relation': [{'id': keyword_id}]},
            '상태': {'select': {'name': 'REVIEW'}},
            '파이프라인 단계': {'select': {'name': 'REVIEW'}},
            '검수 승인': {'checkbox': False},
            '고유 요소 체크': {'checkbox': False},
            '원고 버전': {'number': 1},
            '작성 모델': {'rich_text': rich(os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'))},
            '실행 ID': {'rich_text': rich(run_id)}},
        'children': blocks(body)})


def reconcile(keyword_id, run_id, *, dry=False):
    """Recover from ambiguous create response without creating a second draft."""
    matches = content_for_keyword(keyword_id)
    if not matches:
        return False
    print('Existing content found:', [p['id'] for p in matches])
    if not dry:
        keyword_state(keyword_id, 'DONE')
        save_log('Duplicate/recovery', run_id, 'RECOVERY', 'SKIPPED',
                 'Existing content; keyword set DONE', matches[0]['id'])
    return True


def run():
    dry = os.getenv('DRY_RUN', 'true').lower() == 'true'
    run_id = os.getenv('GITHUB_RUN_ID', 'local') + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1')
    selected_id = os.getenv('KEYWORD_PAGE_ID', '').strip()
    if selected_id:
        row = keyword_page(selected_id)
        state = row.get('properties', {}).get('상태', {}).get('select') or {}
        if state.get('name') not in ('READY', 'PROCESSING', 'ERROR'):
            print('Keyword not in retryable state:', state.get('name'))
            return
    else:
        ready = query(KEYWORDS, {'property': '상태', 'select': {'equals': 'READY'}}, 100)
        if not ready:
            print('No READY keyword')
            return
        row = sorted(ready, key=lambda x: x.get('created_time', ''))[0]
    keyword_id, keyword = row['id'], textprop(row, '키워드')
    if not keyword:
        raise ValueError('Empty keyword title')
    if reconcile(keyword_id, run_id, dry=dry):
        return
    print('Selected keyword:', keyword, 'dry_run:', dry)
    if not dry:
        # GitHub concurrency serializes this workflow, but does not lock other writers.
        keyword_state(keyword_id, 'PROCESSING')
        save_log('Keyword claimed', run_id, 'CLAIM', 'STARTED')
    try:
        search = naver_search(keyword)
        sources = verified_sources()
        draft = generate(keyword, search, sources)
        blocks(draft['body'])  # validate before create
        if dry:
            print('DRY RUN title:', draft['title'], 'length:', len(draft['body']))
            return
        # Check again before non-idempotent create; API may have been updated elsewhere.
        if reconcile(keyword_id, run_id):
            return
        saved = save_draft(keyword_id, draft, run_id)
        print('Draft created:', saved.get('url', saved['id']))
        save_log('Draft saved', run_id, 'SAVE', 'SUCCESS', content_id=saved['id'])
        keyword_state(keyword_id, 'DONE')
    except Exception as error:
        if not dry:
            try:
                # If create succeeded but response was lost, this resolves on the next run.
                if not reconcile(keyword_id, run_id):
                    keyword_state(keyword_id, 'ERROR')
                    save_log('Draft failed', run_id, 'RECOVERY', 'FAILED', type(error).__name__)
            except Exception as nested:
                print('Recovery also failed:', type(nested).__name__, file=sys.stderr)
        raise


if __name__ == '__main__':
    run()
