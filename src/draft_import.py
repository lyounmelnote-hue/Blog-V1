"""v4.1: import human-pasted drafts from Notion; deterministic QA, no AI API."""
import os
import re
from . import main

CONTENT = os.getenv('NOTION_CONTENT_DS', main.CONTENT)
DRY = lambda: os.getenv('DRY_RUN', 'true').lower() == 'true'
START, REPORT = '원고 제출', '자동 검수 결과'


def block_text(block):
    data = block.get(block.get('type', ''), {})
    return ''.join(x.get('plain_text', x.get('text', {}).get('content', ''))
                   for x in data.get('rich_text', []))


def get_blocks(page_id):
    result, cursor = [], None
    for _ in range(20):
        suffix = f'?page_size=100&start_cursor={cursor}' if cursor else '?page_size=100'
        data = main.notion('GET', f'/blocks/{page_id}/children{suffix}')
        result.extend(data.get('results', []))
        if not data.get('has_more'):
            return result
        cursor = data.get('next_cursor')
        if not cursor:
            raise ValueError('블록 페이지네이션 커서 누락')
    raise ValueError('블록 페이지네이션 한도 초과')


def extract_draft(blocks):
    """Extract the submitted draft, including Notion nested list/quote blocks."""
    capturing, lines = False, []
    allowed = ('paragraph', 'heading_1', 'heading_2', 'heading_3',
               'bulleted_list_item', 'numbered_list_item', 'quote',
               'to_do', 'code', 'divider', 'table', 'table_row', 'image', 'bookmark', 'callout')

    def append_block(block, depth=0, ancestry=()):
        if depth > 8:
            raise ValueError('중첩 블록 깊이 한도 초과')
        kind = block.get('type', '')
        if kind not in allowed:
            raise ValueError(f'지원하지 않는 원고 블록: {kind}')
        if kind == 'table_row':
            cells = block.get('table_row', {}).get('cells', [])
            values = [''.join(part.get('plain_text', part.get('text', {}).get('content', ''))
                              for part in cell).replace('|', r'\|').replace('\n', ' ')
                      for cell in cells]
            if values:
                lines.append('| ' + ' | '.join(values) + ' |')
            return
        if kind == 'table':
            block_id = block.get('id')
            if not block_id:
                raise ValueError('표 블록 ID 누락')
            children = get_blocks(block_id)
            if not children:
                raise ValueError('표 행이 없는 원고 표')
            for index, child in enumerate(children):
                if child.get('type') != 'table_row':
                    raise ValueError('표 내부에 예상하지 못한 블록')
                append_block(child, depth + 1, ancestry + (block_id,))
                if index == 0 and block.get('table', {}).get('has_column_header'):
                    count = len(child.get('table_row', {}).get('cells', []))
                    lines.append('| ' + ' | '.join(['---'] * count) + ' |')
            return
        text = block_text(block).strip()
        if text:
            prefix = {'heading_1': '# ', 'heading_2': '## ',
                      'heading_3': '### ', 'bulleted_list_item': '- ',
                      'numbered_list_item': '1. ', 'quote': '> '}.get(kind, '')
            lines.append(('  ' * depth) + prefix + text)
        if block.get('has_children'):
            block_id = block.get('id')
            if not block_id:
                raise ValueError('하위 블록 ID 누락')
            if block_id in ancestry:
                raise ValueError('순환 참조 블록')
            for child in get_blocks(block_id):
                append_block(child, depth + 1, ancestry + (block_id,))

    for block in blocks:
        kind, text = block.get('type', ''), block_text(block).strip()
        normalized = re.sub(r'^#{1,6}\s*', '', text).strip()
        if kind in ('heading_1', 'heading_2', 'heading_3') and normalized == START:
            if capturing:
                raise ValueError('원고 제출 섹션 중복')
            capturing = True
            continue
        if capturing and kind in ('heading_1', 'heading_2', 'heading_3') and normalized == REPORT:
            break
        if capturing:
            append_block(block)
    draft = '\n\n'.join(lines).strip()
    if len(draft) > 100000:
        raise ValueError('원고가 최대 글자 수를 초과함')
    return draft


def qa(draft):
    """Rules-based structural check, NOT independent fact-checking."""
    errors, warnings = [], []
    body = draft.strip()
    compact = re.sub(r'\s+', '', body)
    if len(compact) < 500:
        errors.append('본문 500자 미만(공백 제외)')
    if len(compact) > 20000:
        warnings.append('본문 20,000자 초과')
    if not re.search(r'(?m)^#{1,3}\s*\S+', body):
        warnings.append('Markdown 소제목을 찾지 못함')
    if not re.search(r'https?://[^\s)\]>]+', body):
        warnings.append('본문에 참고 출처 URL이 없음')
    if not re.search(r'#[가-힣A-Za-z0-9_]{2,}', body):
        warnings.append('해시태그가 없음')
    if re.search(r'(무조건|100%\s*(?:보장|확실)|반드시\s*완치|기적의\s*치료)', body, re.I):
        warnings.append('과장 또는 효과 단정 표현 검토 필요')
    if re.search(r'(?i)(lorem ipsum|\[내용 입력\]|\[출처 입력\]|TODO|TBD)', body):
        errors.append('미완성 자리표시자 발견')
    if re.search(r'(?i)(openai[_-]?api[_-]?key|sk-[A-Za-z0-9]{20,}|notion_secret_[A-Za-z0-9]+)', body):
        errors.append('비밀키로 의심되는 문자열 발견')
    return {'passed': not errors, 'errors': errors, 'warnings': warnings,
            'characters': len(compact),
            'checks': '규칙 기반 형식·분량·표현·비밀정보 검사. 사실 검증·저작권 판정 아님'}


def report_blocks(result):
    msg = ('검수 결과: ' + ('형식 검사 통과(사람 검수 필요)' if result['passed'] else '수정 필요') +
           f" | 공백 제외 {result['characters']}자\n" +
           '오류: ' + ('; '.join(result['errors']) or '없음') + '\n' +
           '주의: ' + ('; '.join(result['warnings']) or '없음') + '\n' + result['checks'])
    return [
        {'object': 'block', 'type': 'heading_2',
         'heading_2': {'rich_text': main.rich(REPORT)}},
        {'object': 'block', 'type': 'paragraph',
         'paragraph': {'rich_text': main.rich(msg)}}
    ]


def process(page):
    page_id = page['id']
    props = page.get('properties', {})
    if (props.get('집필 요청 상태', {}).get('select') or {}).get('name') != 'PROMPT_READY':
        return 'skipped'
    blocks = get_blocks(page_id)
    report_indices = [i for i, b in enumerate(blocks)
                      if b.get('type') in ('heading_1', 'heading_2', 'heading_3')
                      and block_text(b).strip() == REPORT]
    if report_indices:
        # Recover a partially completed run: QA was appended but status PATCH failed.
        print('IMPORT_REPORT_EXISTS', page_id)
        if not DRY():
            tail = ' '.join(block_text(b) for b in blocks[report_indices[-1] + 1:])
            recovered = 'DRAFT_IMPORTED' if '형식 검사 통과(사람 검수 필요)' in tail else 'NEEDS_REVIEW'
            main.notion('PATCH', f'/pages/{page_id}', json={'properties': {
                '집필 요청 상태': {'select': {'name': recovered}},
                '상태': {'select': {'name': 'REVIEW'}},
                '파이프라인 단계': {'select': {'name': 'REVIEW'}},
                '검수 승인': {'checkbox': False}
            }})
            return 'recovered'
        return 'skipped'
    draft = extract_draft(blocks)
    if not draft:
        print('IMPORT_AWAITING_DRAFT', page_id)
        return 'waiting'
    result = qa(draft)
    print('IMPORT_QA', page_id, 'passed=', result['passed'],
          'errors=', len(result['errors']), 'warnings=', len(result['warnings']),
          'dry_run=', DRY())
    if DRY():
        return 'preview'
    # Preserve the draft and prompt. Append QA first; reruns never append twice.
    main.notion('PATCH', f'/blocks/{page_id}/children', safe_retry=False,
                json={'children': report_blocks(result)})
    state = 'DRAFT_IMPORTED' if result['passed'] else 'NEEDS_REVIEW'
    main.notion('PATCH', f'/pages/{page_id}', json={'properties': {
        '집필 요청 상태': {'select': {'name': state}},
        '상태': {'select': {'name': 'REVIEW'}},
        '파이프라인 단계': {'select': {'name': 'REVIEW'}},
        '검수 승인': {'checkbox': False},
        '원고 버전': {'number': 1},
        '검증 메모': {'rich_text': main.rich(
            'v4.1 규칙 기반 QA: ' + ('통과' if result['passed'] else '수정 필요') +
            '. 사실관계·저작권·이미지·SEO는 사람이 검수해야 함.')}
    }})
    return 'imported' if result['passed'] else 'needs_review'


def run():
    pages = main.query(CONTENT,
                       {'property': '집필 요청 상태',
                        'select': {'equals': 'PROMPT_READY'}}, 100)
    errors = []
    for page in pages:
        try:
            process(page)
        except Exception as exc:
            errors.append(page.get('id'))
            print('IMPORT_ERROR', page.get('id'), type(exc).__name__, str(exc))
    print('IMPORT_SCAN_COMPLETE', 'examined=', len(pages), 'errors=', len(errors))
    if errors:
        raise RuntimeError(f'Draft import failed for {len(errors)} pages')


if __name__ == '__main__':
    run()
