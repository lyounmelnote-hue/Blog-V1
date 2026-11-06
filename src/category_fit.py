"""Conservative editorial topic/intent checks; search seeds are not category evidence."""

TOPICS = {
    '문화': ('공연', '전시', '박물관', '미술', '영화', '신간', '도서', '독서', '음악', '연극', '문화', '축제'),
    '일상': ('일상', '루틴', '산책', '취미', '계절', '기념일', '집밥', '여행', '나들이', '수납', '청소'),
    '생활정보팁': ('신청', '발급', '절약', '요금', '주거', '주택', '청약', '지원금', '정부24', '생활', '정리', '세금', '연금'),
    '건강': ('건강', '질병', '예방', '접종', '검진', '고혈압', '당뇨', '감염', '영양', '운동', '수면', '의료', '진료', '치료', '금연'),
    '핫뉴스': ('과학', '기술', '연구', '우주', '인공지능', '제도', '시행', '개편', '변경', '발견'),
}
INTENTS = {
    '문화': ('관람', '예약', '예매', '일정', '장소', '입장', '감상', '소개', '추천'),
    '일상': ('방법', '루틴', '준비', '추천', '실천', '체험', '코스', '관리'),
    '생활정보팁': ('방법', '신청', '대상', '조건', '기간', '비교', '안내', '확인', '절약', '사용법'),
    '건강': ('예방', '수칙', '관리', '검진', '접종', '증상', '식단', '습관', '대상', '방법', '안내'),
    '핫뉴스': ('발표', '시행', '변경', '도입', '개편', '발견', '영향', '확인', '안내'),
}
NON_MEDICAL_POLICY = ('주택', '주거', '청약', '부동산', '대출', '금리', '관세', '증시', '투자', '분양')


def evaluate(category, item):
    title = item.get('title', '')
    summary = item.get('summary', '')
    if category not in TOPICS:
        return {'accepted': False, 'reason': '알 수 없는 카테고리'}
    anchors = [word for word in TOPICS[category] if word in title]
    support = [word for word in TOPICS[category] if word in summary]
    intent = [word for word in INTENTS[category] if word in title + ' ' + summary]
    reason = ''
    if category == '건강' and any(word in title for word in NON_MEDICAL_POLICY):
        reason = '주거·경제 정책 중심 제목은 건강 분야에서 제외'
    elif not anchors:
        reason = '제목의 중심 주제가 카테고리와 불일치'
    elif not support:
        reason = '본문 요약에 카테고리 주제 근거 부족'
    elif not intent:
        reason = '독자의 검색·활용 의도 근거 부족'
    return {'accepted': not reason, 'reason': reason,
            'title_topics': anchors, 'summary_topics': support, 'reader_intents': intent,
            'method': '제목·검색 요약·독자 의도 규칙 평가; 원문 검증 아님'}
