"""v4.3.1 manual, idempotent score backfill for existing Notion recommendations.

Only writes 추천 점수 and 검증 메모. Never creates, deletes, or changes approval.
"""
import json
import os
from datetime import datetime
from . import daily, editorial_score
from .main import notion, rich, textprop

PREFIX = '[v4.3.1 평가] '
KST = editorial_score.KST


def text_of(prop):
    return ''.join(x.get('plain_text', x.get('text', {}).get('content', ''))
                   for x in prop.get('rich_text', []))


def eligible(row, force=False):
    props = row.get('properties', {})
    score = (props.get('추천 점수') or {}).get('number')
    memo = text_of(props.get('검증 메모') or {})
    if not force and (score is not None or PREFIX in memo):
        return False
    return bool(textprop(row, '후보 제목') and text_of(props.get('한 줄 요약') or {}))


def row_item(row):
    props = row['properties']
    return {
        'title': textprop(row, '후보 제목'),
        'summary': text_of(props.get('한 줄 요약') or {}),
        'url': (props.get('원본 링크') or {}).get('url') or '',
        'published_at': '',
    }


def calculate(rows, lookup=None):
    if lookup is None:
        lookup = daily.blog_result_count
    items = [row_item(row) for row in rows]
    results = []
    for row, item in zip(rows, items):
        phrase = editorial_score.search_phrase(item['title'])
        count = None
        if phrase:
            try:
                count = lookup(phrase)
            except Exception as exc:
                print('BACKFILL_PROXY_UNAVAILABLE', row['id'], type(exc).__name__)
        # Historical records have no reliable article publication timestamp.
        # Score with the same rule-based fallback as the live engine.
        result = editorial_score.score(item, items, count)
        results.append((row, result))
    return results


def patch_payload(row, result):
    props = row.get('properties', {})
    original = text_of(props.get('검증 메모') or {})
    # Preserve the preexisting human/editorial notes; append a bounded audit trail.
    note = PREFIX + json.dumps(result, ensure_ascii=False, separators=(',', ':'))
    note += ' | 과거 기사 발행일 미보관: 시의성은 문구 기반 추정(실제 발행일 아님).'
    if PREFIX in original:
        original = original.split(PREFIX, 1)[0].rstrip()
    combined = (original + '\n' if original else '') + note
    if len(combined) > 1900:
        # Never silently discard existing notes. Skip and report instead.
        raise ValueError('검증 메모 길이 초과: 기존 메모 보존을 위해 수동 검토 필요')
    return {'properties': {
        '추천 점수': {'number': result['total']},
        '검증 메모': {'rich_text': rich(combined)},
    }}


def run():
    date = os.environ.get('BACKFILL_DATE', '').strip()
    if not date:
        raise ValueError('BACKFILL_DATE 필수: YYYY-MM-DD')
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError as exc:
        raise ValueError('BACKFILL_DATE 날짜 형식 오류') from exc
    dry = os.environ.get('DRY_RUN', 'true').lower() != 'false'
    force = os.environ.get('BACKFILL_FORCE', 'false').lower() == 'true'
    rows = daily.existing_day_rows(date)
    if len(rows) > 100:
        raise ValueError('일일 추천 100건 초과: 일괄 수정 중단')
    pending = [row for row in rows if eligible(row, force=force)]
    print('BACKFILL_SCAN', json.dumps({'date': date, 'found': len(rows),
                                      'eligible': len(pending), 'skipped': len(rows)-len(pending),
                                      'dry_run': dry, 'force': force}, ensure_ascii=False))
    errors = []
    for row, result in calculate(pending):
        try:
            payload = patch_payload(row, result)
            print('BACKFILL_SCORE', row['id'], result['total'], json.dumps(result['parts'], ensure_ascii=False))
            if not dry:
                notion('PATCH', '/pages/' + row['id'], json=payload, safe_retry=False)
        except Exception as exc:
            errors.append(row['id'])
            print('BACKFILL_ERROR', row['id'], type(exc).__name__, str(exc))
    print('BACKFILL_COMPLETE', 'updated=', 0 if dry else len(pending)-len(errors),
          'previewed=', len(pending) if dry else 0, 'errors=', len(errors))
    if errors:
        raise RuntimeError('재평가 실패 ' + str(len(errors)) + '건')


if __name__ == '__main__':
    run()
