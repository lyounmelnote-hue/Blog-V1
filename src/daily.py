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
from . import editorial_score

DAILY = os.getenv('NOTION_DAILY_DS', '13615add-6aef-417c-b1f7-ca93217f4cea')
CATEGORIES = ['문화', '일상', '생활정보팁', '건강', '핫뉴스']
SEEDS = {
 '문화':['문화 공연 전시 행사','신간 영화 문화 소식'],
 '일상':['계절 생활 루틴','기념일 일상 정보'],
 '생활정보팁':['정부 생활 정보 안내','가정 생활 절약 정리'],
 '건강':['질병관리청 건강 생활 수칙','보건복지부 건강 예방 안내'],
 '핫뉴스':['과학 기술 공식 발표','생활 제도 변경 공지']}
INTENT_SEEDS = {
 '문화':['전시 일정 예약 방법','도서 추천 비교'],
 '일상':['계절별 준비물 체크리스트','생활 루틴 정리 방법'],
 '생활정보팁':['지원금 신청 대상 방법','생활비 절약 비교'],
 '건강':['질병관리청 예방 수칙','건강검진 준비 방법'],
 '핫뉴스':['새 제도 시행 대상 확인','디지털 서비스 이용 방법']}
DAILY_LIMIT = 10
CATEGORY_TARGET = 2
CATEGORY_MAX = 4
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
             'publisher_url':x.get('link') or '', 'published_at':x.get('pubDate') or '',
             'channel':endpoint, 'search_query':query_text} for x in data.get('items', [])]


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
    """News + blog search with informational intent; all results remain unverified."""
    collected = []
    for seed in SEEDS[category]:
        collected.extend(search(seed, 'news', 8))
    for seed in INTENT_SEEDS[category]:
        collected.extend(search(seed, 'blog', 8))
    return collected


def allocate_ranked(pool, existing_counts, existing_urls, limit=DAILY_LIMIT):
    """Prefer two per category, then fill globally up to four/category."""
    available = []
    seen_urls = set(existing_urls)
    seen_titles = set()
    for category, item in sorted(pool, key=lambda pair: -pair[1]['editorial_score']['total']):
        url = normalized_article_url(item.get('url'))
        title = re.sub(r'\W', '', item.get('title', '')).lower()
        if not url or url in seen_urls or not title or title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        available.append((category, item))
    counts = Counter(existing_counts)
    selected = []
    capacity = max(0, limit - sum(counts.values()))
    for ceiling in (CATEGORY_TARGET, CATEGORY_MAX):
        for category, item in available:
            if len(selected) >= capacity:
                break
            if (category, item) in selected or counts[category] >= ceiling:
                continue
            selected.append((category, item))
            counts[category] += 1
    return selected


def run():
    dry = os.getenv('DRY_RUN', 'true').lower() == 'true'
    date = os.getenv('RECOMMEND_DATE') or date_kst()
    run_id = os.getenv('GITHUB_RUN_ID', 'local') + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1')
    review_queue = os.getenv('REVIEW_QUEUE', 'true').lower() == 'true'
    day_rows = existing_day_rows(date)
    counts = existing_category_counts(day_rows)
    used_urls = existing_day_urls(day_rows)
    print('DEDUP_DIAGNOSTICS', json.dumps({'date':date, 'existing_rows':len(day_rows),
          'categories':dict(counts), 'existing_urls':len(used_urls)}, ensure_ascii=False))
    if len(day_rows) >= DAILY_LIMIT:
        print('DAILY_LIMIT_REACHED', len(day_rows))
        return
    if not review_queue:
        raise RuntimeError('v4.5.1 requires REVIEW_QUEUE=true; verified pipeline unchanged')
    pool = []
    stats = {}
    for category in CATEGORIES:
        raw = collect_candidates(category)
        candidates = dedupe_candidates(raw, used_urls)
        eligible, rejected = queue_shortlist(candidates, limit=len(candidates))
        # Score all eligible candidates, but cap network calls per category.
        ranked = editorial_score.rank(eligible[:24], blog_result_count, top=24)
        pool.extend((category, item) for item in ranked)
        stats[category] = {'collected':len(raw), 'eligible':len(eligible),
                           'rejected':len(rejected), 'reasons':rejection_report(rejected)}
    chosen = allocate_ranked(pool, counts, used_urls)
    print('COLLECTION_DIAGNOSTICS', json.dumps(stats, ensure_ascii=False))
    print('ALLOCATION_DIAGNOSTICS', json.dumps({'selected':len(chosen),
          'missing':max(0, DAILY_LIMIT-len(day_rows)-len(chosen)),
          'categories':dict(Counter(c for c,_ in chosen))}, ensure_ascii=False))
    for offset, (category, item) in enumerate(chosen, start=1):
        counts[category] += 1
        slot = len(day_rows) + offset
        print('REVIEW_QUEUE', category, slot, item['editorial_score']['total'], item['title'])
        if dry:
            continue
        source = create_unverified_source(item)
        save_review_candidate(date, category, slot, item, run_id, source['id'])
    missing = max(0, DAILY_LIMIT-len(day_rows)-len(chosen))
    if missing and not dry:
        save_log('추천 후보 부족', run_id, 'RESEARCH', 'SKIPPED',
                 f'{date}: {missing}개 부족; 검증 조건 완화 없이 보류')
    print(json.dumps({'date':date, 'dry_run':dry, 'review_queue':review_queue,
                      'selected':len(chosen), 'missing':missing}, ensure_ascii=False))


if __name__=='__main__':
    run()
