"""v4.4 read-only editorial score vs published performance report.

No AI APIs, no Notion writes, no automatic weight tuning.
"""
import csv
import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .main import CONTENT, query, textprop, notion
import requests

ANALYTICS = os.getenv('NOTION_ANALYTICS_DS', 'db3e1b5b-1016-498f-99d5-919aa7d262b3')
OUT = Path(os.getenv('REPORT_DIR', 'reports/v4.4'))
KST = timezone(timedelta(hours=9))


def rel(page, key):
    return [v['id'] for v in page.get('properties', {}).get(key, {}).get('relation', []) if v.get('id')]


def number(page, key):
    value = page.get('properties', {}).get(key, {}).get('number')
    return float(value) if isinstance(value, (float, int)) and math.isfinite(value) and value >= 0 else None


def day(page, key):
    raw = ((page.get('properties', {}).get(key, {}).get('date') or {}).get('start') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def state(page):
    return ((page.get('properties', {}).get('상태', {}).get('select') or {}).get('name') or '')


def latest_analytics(rows):
    """Latest measurement per (content, day), not a sum of cumulative snapshots."""
    result = {}
    for row in rows:
        measurement = day(row, '측정일')
        if measurement is None:
            continue
        for content_id in rel(row, '콘텐츠'):
            key = (content_id, measurement)
            previous = result.get(key)
            if previous is None or (row.get('last_edited_time', ''), row['id']) > (
                    previous.get('last_edited_time', ''), previous['id']):
                result[key] = row
    return result


def score_from_recommendations(content, recommendation_by_id):
    ids = rel(content, '일일 추천')
    scores = [number(recommendation_by_id[i], '추천 점수')
              for i in ids if i in recommendation_by_id]
    scores = [s for s in scores if s is not None]
    if len(scores) != 1:
        return None, '추천 점수 누락/다중 추천' if not scores or len(scores) > 1 else ''
    return scores[0], ''


def report(contents, analytics, recommendations, as_of=None, min_age_days=7):
    today = as_of or datetime.now(KST).date()
    rec_by_id = {r['id']: r for r in recommendations}
    snapshots = latest_analytics(analytics)
    grouped = defaultdict(list)
    for (content_id, measured), row in snapshots.items():
        grouped[content_id].append((measured, row))
    output = []
    for content in contents:
        content_id = content['id']
        published = day(content, '실제 발행일')
        score, reason = score_from_recommendations(content, rec_by_id)
        if state(content) != '발행 완료' or not published:
            reason = '미발행 또는 실제 발행일 누락'
        elif (today - published).days < min_age_days:
            reason = '발행 후 관찰 기간 부족'
        elif score is None:
            reason = reason or '추천 점수 누락'
        eligible = not reason
        # Compare a common 7-day observation window, not arbitrary lifetime totals.
        within = [(d, r) for d, r in grouped[content_id]
                  if published <= d <= min(published + timedelta(days=7), today)]
        last = max(within, key=lambda x: x[0]) if within else None
        views = number(last[1], '조회수') if last else None
        likes = number(last[1], '공감 수') if last else None
        shares = number(last[1], '공유 수') if last else None
        comments = number(last[1], '댓글 수') if last else None
        if eligible and views is None:
            eligible, reason = False, '발행 7일 내 조회수 측정치 없음'
        output.append({
            'content_id': content_id,
            'title': textprop(content, '제목'),
            'published': published.isoformat() if published else '',
            'recommendation_score': score,
            'views_7d_snapshot': views,
            'likes_7d_snapshot': likes,
            'shares_7d_snapshot': shares,
            'comments_7d_snapshot': comments,
            'last_measurement': last[0].isoformat() if last else '',
            'eligible': eligible,
            'exclusion_reason': reason,
        })
    comparable = [r for r in output if r['eligible']]
    result = {'as_of': today.isoformat(), 'total_contents': len(output),
              'comparable': len(comparable),
              'excluded': len(output)-len(comparable),
              'limitations': [
                  '7일 이내 마지막 측정 스냅샷을 사용하며 정확한 7일차 조회수가 아닐 수 있음',
                  '조회수는 누적 스냅샷으로 간주; 일별 수치를 합산하지 않음',
                  '추천 점수와 성과의 상관관계는 인과관계가 아님',
                  '네이버 블로그 성과는 수동으로 BLOG_ANALYTICS에 기록해야 함',
                  '동일 콘텐츠의 중복 일자 측정은 마지막 수정된 행만 사용',
              ]}
    if len(comparable) >= 5:
        result['spearman_score_vs_views'] = spearman(
            [r['recommendation_score'] for r in comparable],
            [r['views_7d_snapshot'] for r in comparable])
    else:
        result['spearman_score_vs_views'] = None
        result['interpretation'] = '비교 가능한 발행 콘텐츠 5건 미만: 상관 분석 보류'
    return result, output


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0]*len(values)
    for start in range(len(order)):
        if start and values[order[start]] == values[order[start-1]]:
            continue
        end = start
        while end+1 < len(order) and values[order[end+1]] == values[order[start]]:
            end += 1
        for j in range(start, end+1):
            out[order[j]] = (start + end)/2 + 1
    return out


def spearman(a, b):
    if len(a) != len(b) or len(a) < 2:
        return None
    x, y = ranks(a), ranks(b)
    xm, ym = sum(x)/len(x), sum(y)/len(y)
    den = math.sqrt(sum((v-xm)**2 for v in x) * sum((v-ym)**2 for v in y))
    return round(sum((u-xm)*(v-ym) for u,v in zip(x,y))/den, 4) if den else None


def fetch_analytics_rows():
    try:
        return query(ANALYTICS, page_size=100)
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise
        # Notion API database ID may differ from the data-source ID.
        try:
            parent = notion('GET', '/databases/' + ANALYTICS)
        except requests.HTTPError as discovery_exc:
            if discovery_exc.response is not None and discovery_exc.response.status_code == 404:
                raise RuntimeError(
                    'BLOG_ANALYTICS 404: GitHub NOTION_TOKEN 통합에 DB를 공유하고 '
                    '실제 data_source ID를 NOTION_ANALYTICS_DS에 지정하세요. '
                    'ChatGPT Notion 연결 권한과 GitHub 토큰 권한은 별개입니다.'
                ) from discovery_exc
            raise
        sources = parent.get('data_sources') or []
        if len(sources) != 1 or not sources[0].get('id'):
            raise RuntimeError('BLOG_ANALYTICS의 데이터 소스가 0개 또는 여러 개입니다. '
                               '실제 data_source ID를 NOTION_ANALYTICS_DS로 지정하세요.') from exc
        resolved = sources[0]['id']
        print('V44_RESOLVED_ANALYTICS_DS', resolved)
        return query(resolved, page_size=100)


def run():
    contents = query(CONTENT, page_size=100)
    analytics = fetch_analytics_rows()
    from .daily import DAILY
    recommendations = query(DAILY, page_size=100)
    summary, rows = report(contents, analytics, recommendations)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    with (OUT/'content_metrics.csv').open('w', newline='', encoding='utf-8-sig') as fp:
        writer = csv.DictWriter(fp, fieldnames=[
            'content_id','title','published','recommendation_score','views_7d_snapshot',
            'likes_7d_snapshot','shares_7d_snapshot','comments_7d_snapshot',
            'last_measurement','eligible','exclusion_reason'])
        writer.writeheader()
        writer.writerows(rows)
    print('V44_ANALYTICS', json.dumps(summary, ensure_ascii=False))
    print('V44_REPORT_FILES', str(OUT/'summary.json'), str(OUT/'content_metrics.csv'))


if __name__ == '__main__':
    run()
