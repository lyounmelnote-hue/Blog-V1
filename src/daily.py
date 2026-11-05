"""Fail-closed daily recommendation queue. No automatic publishing."""
import html
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from collections import Counter
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from .main import notion, query, request, rich, textprop, SOURCES, CONTENT, KEYWORDS, save_log
from . import editorial_score, topic_dedupe

DAILY = os.getenv('NOTION_DAILY_DS', '13615add-6aef-417c-b1f7-ca93217f4cea')
CATEGORIES = ['문화', '일상', '생활정보팁', '건강', '핫뉴스']
SEEDS = {
 '문화':['문화 공연 전시 행사','신간 영화 문화 소식'],
 '일상':['계절 생활 루틴','기념일 일상 정보'],
 '생활정보팁':['정부 생활 정보 안내','가정 생활 절약 정리'],
 '건강':['질병관리청 건강 생활 수칙','보건복지부 건강 예방 안내'],
 '핫뉴스':['과학 기술 공식 발표','생활 제도 변경 공지']}
BLOCKED = ['선거','대선','총선','정당','정치인','혐오','폭행','살인','성범죄','불륜','루머','수사 중','재판 중','갈등','전쟁','자살','극단적 선택']
OFFICIAL_DOMAINS = ('go.kr','or.kr','ac.kr','kopis.or.kr')


def clean(s):
    return re.sub(r'<[^>]*>', '', html.unescape(s or '')).strip()


def domain(url):
    host = urlparse(url).hostname or ''
    return host.removeprefix('www.').lower()


def is_official(url):
    host = domain(url)
    return any(host == suffix or host.endswith('.' + suffix) for suffix in OFFICIAL_DOMAINS)


def search(query_text, endpoint='news', count=10):
    data = request('GET', f'https://openapi.naver.com/v1/search/{endpoint}.json',
       headers={'X-Naver-Client-Id':os.environ['NAVER_CLIENT_ID'],
                'X-Naver-Client-Secret':os.environ['NAVER_CLIENT_SECRET']},
       params={'query':query_text,'display':count,'sort':'date' if endpoint=='news' else 'sim'})
    return [{'title':clean(x.get('title')),'summary':clean(x.get('description')),
             'url':x.get('originallink') or x.get('link') or '',
             'publisher_url':x.get('link') or '', 'published_at':x.get('pubDate') or ''} for x in data.get('items', [])]


def curated_sources():
    rows = query(SOURCES, {'property':'검증 상태','select':{'equals':'검증 완료'}}, page_size=100)
    output=[]
    for p in rows:
        props=p.get('properties',{})
        u=props.get('URL',{}).get('url') or props.get('userDefined:URL',{}).get('url')
        if u and props.get('원문 확인 여부',{}).get('checkbox') is True:
            output.append({'id':p['id'],'title':textprop(p,'자료명'),'url':u,'evidence':textprop(p,'주요 근거')})
    return output


def source_check(category, item, related):
    """Evidence is deliberately conservative: title overlap is NOT proof of a claim."""
    title=item['title']
    official=[s for s in related if is_official(s['url']) and s['evidence'] and any(t in (s['title']+' '+s['evidence']) for t in re.findall(r'[가-힣]{3,}',title)[:6])]
    if category=='건강':
        return (bool(official), official[:2], '건강: 확인된 공공기관 근거 필요')
    if official:
        return True,official[:2],''
    # The Naver Search API cannot prove two reports are independent or substantiate each assertion.
    return False, [], '공식 원문 또는 수동 검증된 출처 부족'


def rule_gate(category, item):
    """Conservative screening; a clean rule result is NOT human approval."""
    text = (item.get('title', '') + ' ' + item.get('summary', '')).lower()
    risky = BLOCKED + ['논란', '논쟁', '혐의', '폭로', '고발', '체포', '피해자', '사망', '학대', '충격', '공포', '완치', '기적의 치료', '반드시 낫']
    matches = [term for term in risky if term in text]
    if matches:
        return {'A': '제외', 'C': '제외', 'reason': '위험 표현: ' + ', '.join(matches[:4])}
    if not item.get('title') or not item.get('summary'):
        return {'A': '주의', 'C': '주의', 'reason': '제목 또는 요약 누락'}
    return {'A': '주의', 'C': '주의', 'reason': '규칙 통과, 사람 검토 필요'}


def shortlist(category, candidates, sources, judge=rule_gate):
    accepted=[]; rejected=[]; seen=set()
    for item in candidates:
        key=re.sub(r'\W','',item['title']).lower()
        if not key or key in seen: continue
        seen.add(key)
        if any(w in item['title']+' '+item['summary'] for w in BLOCKED):
            rejected.append((item,'A: 금지 사전'));continue
        ok,evidence,why=source_check(category,item,sources)
        if not ok:
            rejected.append((item,'B: '+why));continue
        try: verdict=judge(category,item)
        except Exception as e:
            rejected.append((item,'A/C: 심사 실패 '+type(e).__name__));continue
        if verdict['A']=='제외' or verdict['C']=='제외':
            rejected.append((item,'A/C: '+str(verdict.get('reason','주의 이상'))));continue
        score=min(100,60+len(evidence)*10+min(len(item['summary'])//30,10))
        accepted.append((score,item,evidence))
    return sorted(accepted,key=lambda x:-x[0])[:2],rejected



def queue_shortlist(candidates, limit=2):
    """Unverified review queue: never treat a search result as verified evidence."""
    selected, rejected, seen = [], [], set()
    for item in candidates:
        key = re.sub(r'\W', '', item.get('title', '')).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        if not item.get('url') or not urlparse(item['url']).scheme in ('http', 'https'):
            rejected.append((item, 'B: 원문 URL 없음')); continue
        verdict = rule_gate('', item)
        if verdict['A'] == '제외' or verdict['C'] == '제외':
            rejected.append((item, 'A/C: ' + verdict['reason'])); continue
        if not item.get('summary'):
            rejected.append((item, 'C: 요약 누락')); continue
        if len(selected) < limit:
            selected.append(item)
    return selected, rejected


def blog_result_count(phrase):
    """Naver blog result TOTAL: interest/supply proxy, NOT actual search volume."""
    data = request('GET', 'https://openapi.naver.com/v1/search/blog.json',
       headers={'X-Naver-Client-Id':os.environ['NAVER_CLIENT_ID'],
                'X-Naver-Client-Secret':os.environ['NAVER_CLIENT_SECRET']},
       params={'query':phrase,'display':1,'sort':'sim'})
    return data.get('total')


def ranked_review_shortlist(candidates, limit=2):
    """Existing safety filter remains mandatory; ranking never bypasses it."""
    eligible, rejected = queue_shortlist(candidates, limit=len(candidates))
    # Cap extra API calls at 12 per category to bound rate and latency.
    ranked = editorial_score.rank(eligible[:12], blog_result_count, top=limit)
    return ranked, rejected


def create_unverified_source(item):
    """Article URL is a research lead, NOT a verified supporting citation."""
    props = {
        '자료명': {'title': rich(item['title'][:150])},
        'URL': {'url': item['url']},
        '검증 상태': {'select': {'name': '미검증'}},
        '원문 확인 여부': {'checkbox': False},
    }
    return notion('POST', '/pages', safe_retry=False, json={
        'parent': {'type': 'data_source_id', 'data_source_id': SOURCES},
        'properties': props})


def save_review_candidate(date, category, slot, item, run_id, source_id):
    props = {
        '후보 제목': {'title': rich(item['title'][:150])},
        '추천일': {'date': {'start': date}},
        '분야': {'select': {'name': category}},
        '슬롯 번호': {'number': slot},
        '한 줄 요약': {'rich_text': rich(item['summary'][:1800])},
        '논란도': {'select': {'name': '주의'}},
        '신빙성': {'select': {'name': '주의'}},
        '불쾌도': {'select': {'name': '주의'}},
        '상태': {'select': {'name': '보류'}},
        '추천 점수': {'number': item.get('editorial_score', {}).get('total', 0)},
        '실행 ID': {'rich_text': rich(run_id)},
        '원본 링크': {'url': item['url']},
        '근거 출처': {'relation': [{'id': source_id}]},
        '검증 메모': {'rich_text': rich('검증 대기: 출처 UNVERIFIED, 원문 확인 필요. ' + json.dumps(item.get('editorial_score', {}), ensure_ascii=False)[:1300])},
    }
    return notion('POST', '/pages', safe_retry=False, json={
        'parent': {'type': 'data_source_id', 'data_source_id': DAILY},
        'properties': props})

def rejection_report(rejected):
    """Aggregated editorial diagnostics; never logs secrets or full source text."""
    counts = Counter()
    for _item, reason in rejected:
        prefix = reason.split(':', 1)[0].strip()
        counts[prefix if prefix in ('A', 'B', 'C', 'A/C') else 'OTHER'] += 1
    return dict(sorted(counts.items()))


def source_report(sources):
    return {'verified_usable_sources': len(sources),
            'official_usable_sources': sum(is_official(s['url']) for s in sources)}


def date_kst():
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def normalized_article_url(url):
    """Canonicalize a news URL for conservative within-day duplicate detection."""
    try:
        u = urlparse((url or '').strip())
        if u.scheme.lower() not in ('http', 'https') or not u.hostname:
            return ''
        host = u.hostname.lower().removeprefix('www.')
        port = (':' + str(u.port)) if u.port and u.port not in (80, 443) else ''
        path = u.path.rstrip('/') or '/'
        params = sorted((k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                        if not (k.lower().startswith('utm_') or k.lower() in
                                    ('fbclid', 'gclid', 'ref', 'source')))
        return urlunparse(('https', host + port, path, '', urlencode(params), ''))
    except (ValueError, TypeError):
        return ''


def existing_day_rows(date):
    """Fetch all rows for the date (including pagination) to avoid cross-category duplicates."""
    return query(DAILY, {'property': '추천일', 'date': {'equals': date}}, page_size=100)


def existing_category_counts(rows):
    counts = Counter()
    for row in rows:
        category = (row.get('properties', {}).get('분야', {}).get('select') or {}).get('name')
        if category:
            counts[category] += 1
    return counts


def existing_day_urls(rows):
    urls = set()
    for row in rows:
        props = row.get('properties', {})
        url = normalized_article_url((props.get('원본 링크') or {}).get('url'))
        if url:
            urls.add(url)
    return urls


def dedupe_candidates(candidates, existing_urls):
    """Remove existing-day URLs and duplicate URLs within this batch."""
    result, seen = [], set(existing_urls)
    for item in candidates:
        url = normalized_article_url(item.get('url'))
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        result.append(item)
    return result


def already_created(date, category):
    return query(DAILY,{'and':[{'property':'추천일','date':{'equals':date}},
                               {'property':'분야','select':{'equals':category}}]},page_size=20)


def save_candidate(date, category, slot, score, item, evidence, run_id):
    props={'후보 제목':{'title':rich(item['title'][:150])},'추천일':{'date':{'start':date}},
           '분야':{'select':{'name':category}},'슬롯 번호':{'number':slot},
           '한 줄 요약':{'rich_text':rich(item['summary'][:1800])},
           '논란도':{'select':{'name':'주의'}},'신빙성':{'select':{'name':'안전'}},
           '불쾌도':{'select':{'name':'주의'}},'추천 점수':{'number':score},
           '상태':{'select':{'name':'보류'}},'실행 ID':{'rich_text':rich(run_id)},
           '원본 링크':{'url':item['url']},
           '근거 출처':{'relation':[{'id':s['id']} for s in evidence]},
           '검증 메모':{'rich_text':rich('규칙 검사만 완료. 논란도·불쾌도는 사람이 확인 후 안전으로 변경해야 합니다.')}}
    return notion('POST','/pages',safe_retry=False,json={
        'parent':{'type':'data_source_id','data_source_id':DAILY},'properties':props})


def collect_candidates(category):
    """Collect intent-led news and blog leads; search hits are never verified evidence."""
    leads = []
    for seed in SEEDS[category]:
        for endpoint in ('news', 'blog'):
            for item in search(seed, endpoint, 8):
                item = dict(item)
                item['search_endpoint'] = endpoint
                leads.append(item)
    return leads


def choose_flexible(pool, existing_counts, capacity=10):
    """Prefer two per category; fill remaining slots globally by score."""
    slots = {cat: max(0, 2 - existing_counts.get(cat, 0)) for cat in CATEGORIES}
    available = max(0, capacity - sum(existing_counts.values()))
    chosen = []
    remaining = {cat: list(pool.get(cat, [])) for cat in CATEGORIES}
    for cat in CATEGORIES:
        take = min(slots[cat], available, len(remaining[cat]))
        chosen.extend((cat, item) for item in remaining[cat][:take])
        remaining[cat] = remaining[cat][take:]
        available -= take
    overflow = sorted(((cat, item) for cat in CATEGORIES for item in remaining[cat]),
                      key=lambda pair: (-pair[1]['editorial_score']['total'], pair[1].get('title', '')))
    chosen.extend(overflow[:available])
    return chosen


def run():
    dry = os.getenv('DRY_RUN', 'true').lower() == 'true'
    date = os.getenv('RECOMMEND_DATE') or date_kst()
    run_id = os.getenv('GITHUB_RUN_ID', 'local') + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1')
    review_queue = os.getenv('REVIEW_QUEUE', 'true').lower() == 'true'
    day_rows = existing_day_rows(date)
    counts = existing_category_counts(day_rows)
    remaining = max(0, 10 - len(day_rows))
    print('DEDUP_DIAGNOSTICS', json.dumps({'date': date, 'existing_rows': len(day_rows),
          'categories': dict(counts), 'remaining': remaining}, ensure_ascii=False))
    if not remaining:
        print('CAPACITY_REACHED', date)
        return
    sources = [] if review_queue else curated_sources()
    history = topic_dedupe.historical_rows(query, DAILY, date, days=7)
    seen = list(history) + list(day_rows)
    pool = {}
    audit = []
    for category in CATEGORIES:
        raw = collect_candidates(category)
        novel, duplicates = topic_dedupe.filter_duplicates(raw, seen)
        audit.extend((category, item, match) for item, match in duplicates)
        if review_queue:
            eligible, rejected = queue_shortlist(novel, limit=len(novel))
            ranked = editorial_score.rank(eligible[:24], blog_result_count, top=len(eligible[:24]))
        else:
            accepted, rejected = shortlist(category, novel, sources)
            ranked = []
            for score, item, evidence in accepted:
                ranked.append(dict(item, editorial_score={'total': score}, verified_evidence=evidence))
        pool[category] = ranked
        print('COLLECT_DIAGNOSTICS', json.dumps({'category': category, 'raw': len(raw),
              'novel': len(novel), 'duplicates': len(duplicates), 'eligible': len(ranked),
              'rejected': rejection_report(rejected)}, ensure_ascii=False))
        # Reserve unique candidates across categories, not merely the selected top two.
        for item in ranked:
            seen.append({'id': 'candidate', 'properties': {
                '후보 제목': {'title': [{'plain_text': item['title']}]},
                '원본 링크': {'url': item.get('url', '')}}})
    selected = choose_flexible(pool, counts)
    # Recheck the final shortlist across categories, then backfill unique candidates.
    final_selected = []
    selected_seen = list(history) + list(day_rows)
    for category, item in selected:
        match = topic_dedupe.duplicate_match(item, selected_seen)
        if match:
            audit.append((category, item, match))
            continue
        final_selected.append((category, item))
        selected_seen.append({'id': 'selected', 'properties': {
            '후보 제목': {'title': [{'plain_text': item['title']}]},
            '원본 링크': {'url': item.get('url', '')}}})
    chosen_ids = {id(item) for _, item in selected}
    overflow = sorted(((cat, item) for cat in CATEGORIES for item in pool[cat]
                       if id(item) not in chosen_ids),
                      key=lambda pair: (-pair[1]['editorial_score']['total'], pair[1].get('title', '')))
    for category, item in overflow:
        if len(final_selected) >= remaining:
            break
        match = topic_dedupe.duplicate_match(item, selected_seen)
        if match:
            audit.append((category, item, match))
            continue
        final_selected.append((category, item))
        selected_seen.append({'id': 'selected', 'properties': {
            '후보 제목': {'title': [{'plain_text': item['title']}]},
            '원본 링크': {'url': item.get('url', '')}}})
    selected = final_selected
    # An item that is already a same-day candidate must never be saved twice.
    print('FLEXIBLE_ALLOCATION', json.dumps({'existing': len(day_rows), 'selected': len(selected),
          'remaining_unfilled': remaining - len(selected),
          'by_category': dict(Counter(cat for cat, _ in selected))}, ensure_ascii=False))
    for category, item, match in audit:
        print('TOPIC_DEDUP', json.dumps({'category': category, 'type': match['type'],
              'prior_id': match['prior_id'], 'prior_date': match['prior_date']}, ensure_ascii=False))
        if not dry:
            save_log('중복 소재: ' + item['title'][:90], run_id, 'RESEARCH', 'SKIPPED',
                     json.dumps({'version': 'v4.5.2', 'type': match['type'],
                                 'prior_id': match['prior_id'], 'prior_date': match['prior_date']}, ensure_ascii=False))
    used_slots = {int((r.get('properties', {}).get('슬롯 번호') or {}).get('number') or 0)
                  for r in day_rows}
    free_slots = [n for n in range(1, 11) if n not in used_slots]
    for (category, item), slot in zip(selected, free_slots):
        print('REVIEW_QUEUE' if review_queue else 'SELECT', category, slot,
              item['editorial_score']['total'], item['title'])
        if not dry:
            if review_queue:
                source = create_unverified_source(item)
                save_review_candidate(date, category, slot, item, run_id, source['id'])
            else:
                save_candidate(date, category, slot, item['editorial_score']['total'],
                               item, item.get('verified_evidence', []), run_id)
    print('RUN_SUMMARY', json.dumps({'date': date, 'dry_run': dry,
          'review_queue': review_queue, 'selected': len(selected)}, ensure_ascii=False))


if __name__ == '__main__':
    run()
