"""v4.5 balanced ranking; search-result totals are not measured search volume."""
from . import editorial_score as legacy

REFERENCE = ('공식','통계','자료','보고서','비교','체크리스트','가이드','절차','기준','법령','다운로드')

def score(item, peers, blog_count=None, today=None):
    base = legacy.score(item, peers, blog_count, today)
    p = base['parts']
    competition = max(0, min(10, round(10 - .35*p['검색관심도_대리지표'] + p['차별성']/5)))
    search = max(0, min(50, round(p['SEO_적합성']*1.25 + p['실용성']*.6 + competition)))
    timely = max(0, min(20, p['시의성']))
    text = item.get('title','') + ' ' + item.get('summary','')
    cues = min(4, sum(word in text for word in REFERENCE))
    citation = max(0, min(30, round(p['실용성']*.6 + p['차별성']*.45 + cues*2)))
    return {
        'total': search + timely + citation,
        'parts': {'검색유입_잠재력':search, '시의성':timely, '인용저장_잠재력':citation},
        'weights': {'검색유입_잠재력':50, '시의성':20, '인용저장_잠재력':30},
        'search_phrase':base['search_phrase'],
        'blog_result_count':blog_count,
        'source_verified':False,
        'method':'v4.5 규칙 기반 추정. 블로그 검색결과 수는 검색량이 아니며 실제 조회수·인용수를 예측하지 않음.'
    }

def rank(candidates, blog_count_lookup=None, top=2, today=None):
    """Safety/source gates must be applied by the caller before ranking."""
    result=[]
    for original in candidates:
        item=dict(original)
        phrase=legacy.search_phrase(item.get('title',''))
        count=None
        if blog_count_lookup and phrase:
            try:
                count=blog_count_lookup(phrase)
            except Exception as exc:
                print('V45_PROXY_UNAVAILABLE',type(exc).__name__)
        item['editorial_score']=score(item,candidates,count,today)
        result.append(item)
    return sorted(result,key=lambda i:(-i['editorial_score']['total'],i.get('title','')))[:top]
