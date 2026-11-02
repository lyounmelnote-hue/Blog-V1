"""Poll Notion recommendations selected by a human, then create a review draft.

GitHub Actions cron is polling, not a real-time Notion webhook.
"""
import os

from . import main

DAILY = os.getenv('NOTION_DAILY_DS', '13615add-6aef-417c-b1f7-ca93217f4cea')
DRY = lambda: os.getenv('DRY_RUN', 'true').lower() == 'true'


def selection_eligible(page):
    p = page['properties']
    if p.get('상태', {}).get('select', {}).get('name') not in ('선택', '제작중'):
        return False, 'not selected'
    if any(p.get(k, {}).get('select', {}).get('name') != '안전' for k in ('논란도', '신빙성', '불쾌도')):
        return False, 'safety gate not all SAFE'
    if not (p.get('근거 출처', {}).get('relation') or []):
        return False, 'no linked verified evidence'
    if not main.textprop(page, '후보 제목').strip():
        return False, 'missing title'
    return True, ''


def evidence_verified(page):
    """A linked source must actually have VERIFIED status; relation alone is insufficient."""
    ids = [x["id"] for x in page["properties"].get("근거 출처", {}).get("relation", [])]
    if not ids:
        return False
    for source_id in ids:
        source = main.notion("GET", f"/pages/{source_id}")
        status = (source.get("properties", {}).get("검증 상태", {}).get("select") or {}).get("name")
        if status != "VERIFIED":
            return False
    return True


def lookup_keyword(title):
    matches = main.query(main.KEYWORDS, {'property':'키워드', 'title': {'equals':title}}, 50)
    return matches[0] if matches else None


def create_keyword(title, category, url):
    props = {'키워드': {'title': main.rich(title)}, '상태': {'select': {'name':'READY'}},
             '카테고리': {'select': {'name': category}}, '우선순위': {'number':90}}
    if url: props['원본 출처'] = {'url':url}
    return main.notion('POST', '/pages', safe_retry=False, json={
        'parent': {'type':'data_source_id', 'data_source_id':main.KEYWORDS}, 'properties':props})


def update_recommendation(page_id, state=None, content_id=None, reason=None):
    props={}
    if state: props['상태']={'select':{'name':state}}
    if content_id: props['연결 글']={'relation':[{'id':content_id}]}
    if reason: props['검증 메모']={'rich_text':main.rich(reason[:1800])}
    if props: main.notion('PATCH', f'/pages/{page_id}', json={'properties':props})


def process(page):
    rec_id=page['id']
    p=page['properties']
    existing=p.get('연결 글',{}).get('relation',[])
    if existing:
        print('Already linked:', rec_id)
        return 'already-linked'
    ok, reason=selection_eligible(page)
    if not ok:
        print('Skipped:', rec_id, reason)
        if not DRY() and p.get('상태',{}).get('select',{}).get('name')=='선택':
            update_recommendation(rec_id,reason='자동 집필 보류: '+reason)
        return 'skipped'
    if not evidence_verified(page):
        print('Skipped: linked sources not VERIFIED', rec_id)
        if not DRY(): update_recommendation(rec_id,reason='자동 집필 보류: 연결 출처의 VERIFIED 확인 실패')
        return 'skipped'
    title=main.textprop(page,'후보 제목').strip()
    category=p.get('분야',{}).get('select',{}).get('name','')
    url=p.get('원본 링크',{}).get('url')
    kw=lookup_keyword(title)
    if DRY():
        print('DRY RUN selected:', title, 'existing keyword:', bool(kw))
        return 'preview'
    if not kw:
        # On an ambiguous HTTP response, next poll re-queries by exact title.
        kw=create_keyword(title, '생활정보' if category in ('생활정보팁','건강','일상') else '기타', url)
    kw_id=kw['id']
    # This recommendation is processed only after explicit human selection.
    update_recommendation(rec_id,state='제작중')
    contents=main.content_for_keyword(kw_id)
    if not contents:
        state=(kw.get('properties',{}).get('상태',{}).get('select') or {}).get('name')
        if state not in ('READY','ERROR','PROCESSING'):
            main.keyword_state(kw_id,'READY')
        old=os.environ.get('KEYWORD_PAGE_ID')
        os.environ['KEYWORD_PAGE_ID']=kw_id
        try:
            main.run()
        finally:
            if old is None: os.environ.pop('KEYWORD_PAGE_ID',None)
            else: os.environ['KEYWORD_PAGE_ID']=old
        contents=main.content_for_keyword(kw_id)
    if not contents:
        raise RuntimeError('Draft was not created for selected recommendation')
    content_id=contents[0]['id']
    # Preserve any existing keyword relation, link recommendation and assign category.
    main.notion('PATCH',f'/pages/{content_id}',json={'properties':{
        '분야':{'select':{'name':category}},
        '일일 추천':{'relation':[{'id':rec_id}]}}})
    update_recommendation(rec_id,state='제작중',content_id=content_id,
                          reason='초안 생성 완료: 콘텐츠 DB REVIEW에서 사람 검수 후 게시')
    print('Linked draft:',rec_id,content_id)
    return 'created'


def run():
    # Pick selected and interrupted items, max 5 per invocation; all calls are serialized by GH concurrency.
    pages=main.query(DAILY,{'or':[
        {'property':'상태','select':{'equals':'선택'}},
        {'property':'상태','select':{'equals':'제작중'}}]},page_size=50)
    pages=sorted(pages,key=lambda x:x.get('created_time',''))[:5]
    print('Selected recommendations:',len(pages))
    errors=[]
    for page in pages:
        try: process(page)
        except Exception as exc:
            errors.append((page['id'],type(exc).__name__))
            print('Failed selected recommendation:',page['id'],type(exc).__name__)
            if not DRY():
                try: update_recommendation(page['id'],reason='자동 집필 실패: '+type(exc).__name__+'; 다음 실행 재시도')
                except Exception: pass
    if errors:
        raise RuntimeError('Selected recommendation failures: '+str(errors))

if __name__=='__main__':
    run()
