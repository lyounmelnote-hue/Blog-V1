"""Fail-closed daily recommendation queue. No automatic publishing."""
import html
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from collections import Counter
from urllib.parse import urlparse
from .main import notion, query, request, rich, textprop, SOURCES, CONTENT, KEYWORDS, save_log

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
             'publisher_url':x.get('link') or ''} for x in data.get('items', [])]


def curated_sources():
    rows = query(SOURCES, {'property':'검증 상태','select':{'equals':'VERIFIED'}}, page_size=100)
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


def run():
    dry=os.getenv('DRY_RUN','true').lower()=='true'
    date=os.getenv('RECOMMEND_DATE') or date_kst()
    run_id=os.getenv('GITHUB_RUN_ID','local')+'-'+os.getenv('GITHUB_RUN_ATTEMPT','1')
    sources=curated_sources()
    summary={}
    print('SOURCE_DIAGNOSTICS', json.dumps(source_report(sources), ensure_ascii=False))
    for index,category in enumerate(CATEGORIES):
        existing=already_created(date,category)
        if existing:
            print(category,'already exists:',len(existing),'skipping to prevent duplicates');continue
        candidates=[]
        for seed in SEEDS[category]:
            candidates.extend(search(seed,'news',8))
        accepted,rejected=shortlist(category,candidates,sources)
        summary[category]={'selected':len(accepted),'rejected':len(rejected),'missing':2-len(accepted),
                           'rejection_reasons':rejection_report(rejected)}
        print('GATE_DIAGNOSTICS', json.dumps({'category':category, 'counts':rejection_report(rejected)}, ensure_ascii=False))
        # A previous partial run is skipped above; this run may create up to two rows.
        for i,(score,item,evidence) in enumerate(accepted):
            print('SELECT',category,index*2+i+1,item['title'],score)
            if not dry:
                # GitHub concurrency serializes runs of this workflow.
                save_candidate(date,category,index*2+i+1,score,item,evidence,run_id)
        if not dry and len(accepted)<2:
            save_log('슬롯 미충족: '+category,run_id,'RESEARCH','SKIPPED',
                     f'{date}: {2-len(accepted)}개 부족, 필터 제외 {len(rejected)}개')
    print(json.dumps({'date':date,'dry_run':dry,'summary':summary},ensure_ascii=False))


if __name__=='__main__':
    run()
