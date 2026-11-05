"""Seven-day historical topic dedupe; no AI API or automatic approval."""
import re
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qsl, urlencode

STOP = frozenset("오늘 어제 내일 최근 지금 관련 대한 위해 통해 그리고 있는 없는 다시 이번 올해 방법 안내 소식 발표 뉴스 확인 실제 정말".split())
def tokens(title):
    words = re.findall(r"[가-힣A-Za-z0-9]+", (title or "").casefold())
    return set(w for w in words if len(w) >= 2 and w not in STOP)

def topic_key(title):
    return " ".join(sorted(tokens(title)))

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
              "TOPIC" if len(words)>=3 and words==old else None)
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
