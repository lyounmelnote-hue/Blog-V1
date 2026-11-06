import unittest
from datetime import datetime, timezone, timedelta
from src import editorial_v45

class V45Tests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,3,tzinfo=timezone(timedelta(hours=9)))
        self.item={'title':'공공안심글꼴 다운로드 설치 방법 안내',
                   'summary':'공식 자료를 확인하고 사용법 비교 체크리스트 정리',
                   'url':'https://example.org/a','published_at':'2026-11-02T10:00:00+09:00'}
    def test_weights_and_bounds(self):
        x=editorial_v45.score(self.item,[self.item],200,self.now)
        self.assertEqual(x['weights'],{'검색유입_잠재력':50,'시의성':20,'인용저장_잠재력':30})
        self.assertEqual(sum(x['parts'].values()),x['total'])
        self.assertTrue(0<=x['total']<=100)
    def test_no_search_volume_claim(self):
        x=editorial_v45.score(self.item,[self.item],1000000,self.now)
        self.assertIn('검색량이 아니',x['method'])
        self.assertFalse(x['source_verified'])
    def test_lookup_failure_fallback(self):
        x=editorial_v45.rank([self.item],lambda _:1/0,today=self.now)
        self.assertEqual(len(x),1)
        self.assertIsNone(x[0]['editorial_score']['blog_result_count'])
    def test_deterministic_top_ten(self):
        rows=[dict(self.item,title=f'설치 방법 {i}',url=f'https://example.org/{i}') for i in range(12)]
        a=editorial_v45.rank(rows,lambda _:200,top=10,today=self.now)
        b=editorial_v45.rank(rows,lambda _:200,top=10,today=self.now)
        self.assertEqual(a,b)
        self.assertEqual(len(a),10)

    def test_v43_v45_comparison_ten_candidates_read_only(self):
        from src import editorial_score
        rows = []
        topics = [
            '공공안심글꼴 다운로드 설치 방법',
            '겨울철 난방비 절약 방법 비교',
            '도서관 이용 시간 확인 가이드',
            '문화 행사 일정과 예약 방법',
            '가정 생활비 체크리스트 정리',
            '무료 교육 신청 기간 안내',
            '신규 서비스 이용 조건 비교',
            '일상 기록 정리 방법',
            '생활 제도 변경 기준 안내',
            '전시회 관람 준비물 안내',
        ]
        for i, title in enumerate(topics):
            rows.append({'title': title, 'summary': '공식 자료와 사용 방법을 비교하고 확인할 항목 정리',
                         'url': f'https://example.org/{i}', 'published_at': '2026-11-02T10:00:00+09:00'})
        snapshot = [dict(row) for row in rows]
        old = editorial_score.rank(rows, lambda _: 200, top=10, today=self.now)
        new = editorial_v45.rank(rows, lambda _: 200, top=10, today=self.now)
        self.assertEqual(rows, snapshot, 'Scoring must not modify source candidates')
        self.assertEqual(len(old), 10)
        self.assertEqual(len(new), 10)
        self.assertEqual({r['url'] for r in old}, {r['url'] for r in new})
        self.assertTrue(all(r['editorial_score']['weights'] ==
            {'검색유입_잠재력':50, '시의성':20, '인용저장_잠재력':30} for r in new))

    def test_existing_safety_gate_still_rejects_prohibited_topics(self):
        from src.daily import queue_shortlist
        candidates = [
            {'title':'선거 관련 논란', 'summary':'정치인 관련 소식', 'url':'https://example.org/blocked'},
            {'title':'공공안심글꼴 설치 방법', 'summary':'다운로드 방법과 사용법 정리',
             'url':'https://example.org/allowed'},
        ]
        accepted, rejected = queue_shortlist(candidates, limit=10)
        self.assertEqual([r['url'] for r in accepted], ['https://example.org/allowed'])
        self.assertEqual(len(rejected), 1)

if __name__=='__main__':
    unittest.main()
