"""v4.3 deterministic editorial ranking; blog-result count is NOT search volume."""
import math
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))
UTILITY = ('방법','사용법','신청','확인','정리','비교','준비','절약','안내','찾기','변경','지원','혜택','무료','꿀팁','주의사항','체크리스트','예약')
SEO = ('방법','신청','기간','대상','가격','비용','위치','장소','일정','사용법','비교','확인','조건','다운로드','준비물')
NOVEL = ('새롭게','신규','첫','도입','변경','개편','업데이트','출시','시범','확대')
TIME = ('오늘','이번 주','이번달','올해','내년','시작','마감','개최','발표','시행','오픈')
STOP = {'그리고','관련','대한','위한','에서','으로','한다','했다','있다','기자','뉴스','소식','최근','이번','공식'}


def tokens(text):
    return set(t for t in re.findall(r'[가-힣A-Za-z0-9]{2,}', text.lower()) if t not in STOP)


def search_phrase(title):
    """A reproducible proxy query, not a keyword-volume measurement."""
    return ' '.join(list(re.findall(r'[가-힣A-Za-z0-9]{2,}', title))[:4])


def freshness(item, today=None):
    now = today or datetime.now(KST)
    pub = item.get('published_at')
    if pub:
        try:
            try:
                dt = datetime.fromisoformat(pub.replace('Z', '+00:00'))
            except ValueError:
                dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            days = (now - dt.astimezone(KST)).total_seconds() / 86400
            if days < -1:
                return 5
            if days <= 1:
                return 20
            if days <= 3:
                return 17
            if days <= 7:
                return 13
            if days <= 30:
                return 8
            return 3
        except (ValueError, TypeError):
            pass
    text = item.get('title','') + ' ' + item.get('summary','')
    return 10 if any(k in text for k in TIME) else 6


def demand(blog_count):
    """0..20. Naver blog search result TOTAL is a supply/interest proxy, not monthly queries."""
    if blog_count is None:
        return 10
    try:
        n = max(0, int(blog_count))
    except (TypeError, ValueError):
        return 10
    # Extremely saturated subjects do not get unlimited credit.
    if n == 0: return 2
    if n < 100: return 5
    if n < 1000: return 9
    if n < 10000: return 13
    if n < 100000: return 17
    return 20


def usefulness(item):
    text = item.get('title','') + ' ' + item.get('summary','')
    matches = sum(k in text for k in UTILITY)
    return min(25, 7 + 6 * min(matches, 3))


def seo(item):
    title = item.get('title','')
    text = title + ' ' + item.get('summary','')
    matches = sum(k in text for k in SEO)
    title_length = len(title.strip())
    return min(20, 4 + 5 * min(matches, 2) + (6 if 12 <= title_length <= 65 else 0))


def distinctiveness(item, peers):
    title_tokens = tokens(item.get('title',''))
    max_overlap = 0.0
    for peer in peers:
        if peer is item or peer.get('url') == item.get('url'):
            continue
        other = tokens(peer.get('title',''))
        union = title_tokens | other
        if union:
            max_overlap = max(max_overlap, len(title_tokens & other) / len(union))
    text = item.get('title','') + ' ' + item.get('summary','')
    bonus = 5 if any(k in text for k in NOVEL) else 0
    return max(0, min(15, 10 + bonus - round(max_overlap * 12)))


BLOG_PRACTICAL = ('방법','사용법','신청','발급','설치','절약','비교','준비물','체크리스트','대상','조건','기간','주의사항','가이드','정리','예약')
PROMOTIONAL = ('기념식','축사','업무협약','홍보대사','수상식','브랜드 론칭','캠페인 개최','기념행사','성료','기념 축제')

def blog_fit(item):
    """0..15: reader actionability, not measured traffic."""
    text = item.get('title','') + ' ' + item.get('summary','')
    useful = sum(k in text for k in BLOG_PRACTICAL)
    promotion = sum(k in text for k in PROMOTIONAL)
    return max(0, min(15, 5 + min(useful, 3) * 4 - min(promotion, 2) * 6))

def score(item, peers, blog_count=None, today=None):
    parts = {'검색관심도_대리지표': demand(blog_count),
             '시의성': freshness(item, today),
             '실용성': usefulness(item),
             'SEO_적합성': seo(item),
             '차별성': distinctiveness(item, peers),
             '블로그_적합성': blog_fit(item)}
    return {'total': min(100, round(sum(parts.values()) * 100 / 115)), 'parts': parts,
            'search_phrase': search_phrase(item.get('title','')),
            'blog_result_count': blog_count,
            'method': '검색량 실측 아님: 네이버 블로그 검색 결과 총수 대리지표. 6개 항목 규칙 기반 추정.'}


def rank(candidates, blog_count_lookup=None, top=2, today=None):
    """Filter first; rank second. Network errors fall back to neutral demand score."""
    results=[]
    for item in candidates:
        phrase=search_phrase(item.get('title',''))
        count=None
        if blog_count_lookup and phrase:
            try:
                count=blog_count_lookup(phrase)
            except Exception as exc:
                print('DEMAND_PROXY_UNAVAILABLE', type(exc).__name__)
        item=dict(item)
        item['editorial_score']=score(item,candidates,count,today)
        results.append(item)
    return sorted(results,key=lambda i:(-i['editorial_score']['total'],i.get('title','')))[:top]
