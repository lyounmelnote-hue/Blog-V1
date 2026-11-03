"""Prepare a ChatGPT Project writing request; never attempt to create ChatGPT chats via API."""
import os
import re
from . import main

PROJECT_URL = 'https://chatgpt.com/g/g-p-6ae813d2e0148191bb77ff00d428cf9d-beulrogeu-jadonghwa-poseuting-weongo/project'
DAILY = os.getenv('NOTION_DAILY_DS', '13615add-6aef-417c-b1f7-ca93217f4cea')
DRY = lambda: os.getenv('DRY_RUN', 'true').lower() == 'true'

PALETTES = {
    '문화': ('연보라, 크림, 라벤더, 연한 코랄', '전시·공연·책과 문화적 경험을 상징하는 장면'),
    '일상': ('살구, 아이보리, 연한 베이지, 세이지 그린', '일상의 따뜻한 순간을 상징하는 장면'),
    '생활정보팁': ('민트, 크림, 옅은 하늘색, 연회색', '생활 문제 해결과 실용적인 도구를 상징하는 장면'),
    '건강': ('세이지 그린, 크림, 옅은 민트, 연한 피치', '건강한 생활 습관을 상징하는 비의료적 장면'),
    '핫뉴스': ('연한 하늘색, 아이보리, 옅은 네이비, 라이트 그레이', '중립적인 정보 전달을 상징하는 장면'),
}
STYLE = '부드럽고 평면적인 파스텔 일러스트레이션, {palette} 색상 구성, 깔끔하고 미니멀한 구도, 따뜻하고 친근한 분위기, 제목 텍스트를 위한 {space}의 넉넉한 여백, 텍스트 없음, {ratio} 비율의 {scene}'


def image_prompts(title, category):
    palette, scene = PALETTES.get(category, PALETTES['일상'])
    subject = re.sub(r'\s+', ' ', title).strip()
    # Exactly three prompts, all reuse an identical palette and style string.
    return [
        ('썸네일', STYLE.format(palette=palette, space='왼쪽', ratio='16:9', scene=f'{subject} — {scene}, 핵심 소재가 오른쪽에 배치된 대표 장면')),
        ('본문 이미지 1', STYLE.format(palette=palette, space='오른쪽', ratio='4:3', scene=f'{subject} — 핵심 개념을 시각적으로 설명하는 장면')),
        ('본문 이미지 2', STYLE.format(palette=palette, space='왼쪽', ratio='4:3', scene=f'{subject} — 독자가 실천하거나 이해할 수 있는 구체적 상황을 나타내는 장면')),
    ]


def eligible(page):
    props = page['properties']
    if (props.get('상태', {}).get('select') or {}).get('name') != '선택':
        return False, '상태가 선택이 아님'
    if props.get('연결 글', {}).get('relation'):
        return False, '이미 콘텐츠에 연결됨'
    for key in ('논란도', '신빙성', '불쾌도'):
        if (props.get(key, {}).get('select') or {}).get('name') != '안전':
            return False, f'{key} 안전 판정 아님'
    if not props.get('근거 출처', {}).get('relation'):
        return False, '근거 출처 없음'
    return True, ''


def source_details(page):
    results = []
    for rel in page['properties']['근거 출처']['relation']:
        source = main.notion('GET', f"/pages/{rel['id']}")
        p = source['properties']
        if (p.get('검증 상태', {}).get('select') or {}).get('name') != 'VERIFIED':
            raise ValueError('검증되지 않은 출처')
        url = (p.get('URL', {}).get('url') or p.get('userDefined:URL', {}).get('url') or '')
        if not url:
            raise ValueError('출처 URL 없음')
        results.append((main.textprop(source, '자료명'), url))
    return results


def prompt(title, category, summary, sources):
    references = '\n'.join(f'- {name}: {url}' for name, url in sources)
    images = '\n'.join(f'{i}. {label}: {value}' for i, (label, value) in enumerate(image_prompts(title, category), 1))
    return f'''# 블로그 원고 작성 요청\n\n주제: {title}\n분야: {category}\n소재 요약: {summary}\n\n## 검증된 출처 후보\n{references}\n\n## 작성 지침\n- 한국어 네이버 블로그용 정보성 원고를 작성하세요. 제목 대안 3개, 도입, H2/H3 소제목, 본문, 핵심 요약, 해시태그를 포함하세요.\n- 위 출처를 실제로 확인할 수 없는 경우 확인하지 못했다고 표시하고, 사실·수치·날짜를 추측하지 마세요. 출처의 주장을 과장하거나 뉴스 기사 문장을 베끼지 마세요.\n- 정치·갈등·선정·불안 조장 표현을 피하고, 건강 소재는 진단·치료 효과를 단정하지 마세요.\n- 직접 경험·사진·실측 수치 등 사람이 채울 '고유 요소 삽입 위치'를 명확히 표시하세요.\n- 원고의 끝에 아래의 이미지 생성 프롬프트 3개를 **그대로** 출력하세요. 이미지를 실제 생성했다고 주장하지 마세요.\n\n## 이미지 생성 프롬프트 (총 3장: 썸네일 1 + 본문 2)\n{images}\n\n## 원고 출력\n1. 제목 및 대안 제목\n2. 본문 Markdown\n3. 참고 출처(URL)와 사실 확인 필요 항목\n4. 네이버용 해시태그\n5. 이미지 삽입 위치 및 이미지 생성 프롬프트 3개\n6. 사람 검수 체크리스트\n'''


def process(page):
    ok, reason = eligible(page)
    if not ok:
        print('SKIP', page['id'], reason)
        return 'skipped'
    p = page['properties']
    title = main.textprop(page, '후보 제목').strip()
    if not title:
        raise ValueError('후보 제목 누락')
    category = (p.get('분야', {}).get('select') or {}).get('name', '일상')
    summary = main.textprop(page, '한 줄 요약')
    sources = source_details(page)
    if not sources:
        raise ValueError('근거 출처 없음')
    text = prompt(title, category, summary, sources)
    if DRY():
        print('DRY_RUN prompt packet:', title, 'images:', len(image_prompts(title, category)))
        return 'preview'
    # Query existing content by recommendation relation to prevent duplicate pages after ambiguous responses.
    found = main.query(main.CONTENT, {'property': '일일 추천', 'relation': {'contains': page['id']}}, 20)
    if found:
        main.notion('PATCH', f"/pages/{page['id']}", json={'properties': {'상태': {'select': {'name': '제작중'}}, '연결 글': {'relation': [{'id': found[0]['id']}]}}})
        return 'recovered'
    blocks = main.blocks(text)
    content = main.notion('POST', '/pages', safe_retry=False, json={
        'parent': {'type': 'data_source_id', 'data_source_id': main.CONTENT},
        'properties': {
            '제목': {'title': main.rich(title)}, '상태': {'select': {'name': 'QUEUED'}},
            '분야': {'select': {'name': category}},
            '일일 추천': {'relation': [{'id': page['id']}]},
            '집필 방식': {'select': {'name': 'CHATGPT_PROJECT'}},
            '집필 요청 상태': {'select': {'name': 'PROMPT_READY'}},
            '이미지 프롬프트 수': {'number': 3},
            'ChatGPT 프로젝트 URL': {'url': PROJECT_URL},
            '검수 승인': {'checkbox': False},
            '파이프라인 단계': {'select': {'name': 'QUEUED'}},
        }, 'children': blocks})
    main.notion('PATCH', f"/pages/{page['id']}", json={'properties': {
        '상태': {'select': {'name': '제작중'}},
        '연결 글': {'relation': [{'id': content['id']}]},
        '검증 메모': {'rich_text': main.rich('집필 프롬프트 준비 완료. 콘텐츠 페이지의 프롬프트를 복사해 ChatGPT 프로젝트에서 새 채팅으로 실행하세요.')}
    }})
    print('PROMPT_READY', content['id'])
    return 'created'


def run():
    pages = main.query(DAILY, {'property': '상태', 'select': {'equals': '선택'}}, 50)
    errors = []
    print('SELECTED_SCAN', len(pages), 'dry_run=', DRY())
    for page in pages:
        try:
            process(page)
        except Exception as exc:
            print('ERROR', page['id'], type(exc).__name__, str(exc))
            errors.append(page['id'])
    print('SELECTED_SCAN_COMPLETE', 'examined=', len(pages), 'errors=', len(errors))
    if errors:
        raise RuntimeError(f'Failed to prepare {len(errors)} prompt packets')


if __name__ == '__main__':
    run()
