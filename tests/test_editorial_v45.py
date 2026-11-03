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

if __name__=='__main__':
    unittest.main()
