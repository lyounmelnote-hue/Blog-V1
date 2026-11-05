"""Seven-day historical topic dedupe; no AI API or automatic approval."""
import re
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qsl, urlencode

TOPIC_GENERIC = frozenset("전국 지역 정부 정책 제도 지원 관리 사업 서비스 실시 확대 추진 운영 제공 안내 정보 관련 대상".split())
TOPIC_ANCHORS = ("고혈압", "당뇨", "난방비", "보일러", "다자녀", "온누리상품권", "지역화폐", "유치원", "입학", "면세", "환급", "공공안심글꼴", "독감", "백신")
TOPIC_ACTIONS = ("신청", "발급", "설치", "사용", "예방", "확대", "변경", "개편", "도입", "시행", "환급", "지원", "관리", "비교", "절약", "예약", "준비")
STOP = frozenset("오늘 어제 내일 최근 지금 관련 대한 위해 통해 그리고 있는 없는 다시 이번 올해 방법 안내 소식 발표 뉴스 확인 실제 정말".split())
def tokens(title):
    words = re.findall(r"[가-힣A-Za-z0-9]+", (title or "").casefold())
    return set(w for w in words if len(w) >= 2 and w not in STOP)

def topic_key(title):
    return " ".join(sorted(tokens(title)))

def semantic_topic_match(left, right):
    """Conservative same-event match; generic shared words never suffice."""
    a, b = tokens(left), tokens(right)
    if len(a) < 3 or len(b) < 3:
        return False
    shared = a & b
    informative = shared - TOPIC_GENERIC
    anchors = [term for term in TOPIC_ANCHORS if term in left and term in right]
    actions = [term for term in TOPIC_ACTIONS if term in left and term in right]
    overlap = len(shared) / max(1, min(len(a), len(b)))
    return bool(anchors and actions and len(informative) >= 2 and overlap >= 0.4)

def canonical_url(url):
    try:
        p=urlparse(url or "")
        if p.scheme not in ("http","https") or not p.hostname: return ""
        q=urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith("utm_") and k.lower() not in ("fbclid","gclid","ref","source")))
        return "https://"+p.hostname.lower().removeprefix("www.")+p.path.rstrip("/") + ("?"+q if q else "")
    except ValueError:
        return ""

def property_title(row):
    prop=(row.get("properties") or {}).get("후보 제목") or {}
    return "".join(t.get("plain_text",t.get("text",{}).get("content","")) for t in prop.get("title",[]))

def historical_rows(query, ds, run_date, days=7):
    """Look back seven full calendar days, excluding current day (handled by existing-day guard)."""
    d=date.fromisoformat(run_date)
    start=(d-timedelta(days=days)).isoformat()
    return query(ds, {"and":[{"property":"추천일","date":{"on_or_after":start}},
                             {"property":"추천일","date":{"before":run_date}}]},page_size=100)

def duplicate_match(item, previous):
    """Conservative: exact URL or identical title token set; no single-keyword rejection."""
    u=canonical_url(item.get("url"))
    words=tokens(item.get("title"))
    for row in previous:
        props=row.get("properties") or {}
        prev_u=canonical_url((props.get("원본 링크") or {}).get("url"))
        old=tokens(property_title(row))
        kind=("URL" if u and u==prev_u else
              "TOPIC" if len(words)>=3 and words==old else
              "SEMANTIC_TOPIC" if semantic_topic_match(item.get("title",""),property_title(row)) else None)
        if kind:
            return {"type":kind,"prior_id":row.get("id",""),"prior_title":property_title(row),
                    "prior_date":((props.get("추천일") or {}).get("date") or {}).get("start","")}
    return None

def filter_duplicates(items, previous):
    """Returns (novel candidates, duplicate records), with in-batch duplicates tracked."""
    novel=[]; duplicates=[]; seen=list(previous)
    for item in items:
        match=duplicate_match(item,seen)
        if match:
            duplicates.append((item,match))
        else:
            novel.append(item)
            seen.append({"id":"batch","properties":{
                "후보 제목":{"title":[{"plain_text":item.get("title","")}]},
                "원본 링크":{"url":item.get("url","")}}})
    return novel,duplicates
