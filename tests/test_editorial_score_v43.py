import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from src import editorial_score as es
from src import daily


def item(title, summary='사용 방법 및 신청 안내', url='https://example.org/a', pub=''):
    return {'title': title, 'summary': summary, 'url': url, 'published_at': pub}


class EditorialScoreTests(unittest.TestCase):
    def test_score_bounded_and_weights(self):
        a = item('생활비 절약 신청 방법 비교')
        result = es.score(a, [a], 10000)
        self.assertGreaterEqual(result['total'], 0)
        self.assertLessEqual(result['total'], 100)
        self.assertEqual(set(result['parts']), {
            '검색관심도_대리지표', '시의성', '실용성', 'SEO_적합성', '차별성', '블로그_적합성'})

    def test_search_proxy_is_not_actual_volume(self):
        self.assertEqual(es.demand(None), 10)
        self.assertEqual(es.demand(0), 2)
        self.assertEqual(es.demand(200000), 20)
        self.assertIn('실측 아님', es.score(item('생활정보'), [], None)['method'])

    def test_pubdate_rfc822(self):
        now = datetime(2026, 11, 3, tzinfo=timezone(timedelta(hours=9)))
        a = item('신규 생활정보', pub='Mon, 02 Nov 2026 09:00:00 +0900')
        b = item('지난 생활정보', pub='Mon, 02 Nov 2020 09:00:00 +0900')
        self.assertGreater(es.freshness(a, now), es.freshness(b, now))

    def test_distinctiveness_penalizes_overlap(self):
        a = item('생활비 절약 신청 방법')
        similar = item('생활비 절약 신청 방법', url='https://example.org/b')
        different = item('문화 전시 일정 안내', url='https://example.org/c')
        self.assertLess(es.distinctiveness(a, [a, similar]),
                        es.distinctiveness(a, [a, different]))

    def test_rank_prefers_useful_article(self):
        a = item('문화 소식', '전시 소식')
        b = item('생활비 지원 신청 방법 비교', '지원 대상 조건 확인 방법과 준비물 안내',
                 url='https://example.org/b')
        ranked = es.rank([a, b], blog_count_lookup=lambda _: 1000, top=2)
        self.assertEqual(ranked[0]['title'], b['title'])

    def test_proxy_failure_is_neutral(self):
        ranked = es.rank([item('생활비 지원 방법')], lambda _: 1/0)
        self.assertEqual(ranked[0]['editorial_score']['parts']['검색관심도_대리지표'], 10)

    def test_blocked_still_excluded_before_scoring(self):
        bad = item('선거 갈등 폭로', '선거 갈등', url='https://example.org/bad')
        good = item('문화 전시 일정 안내')
        with patch.object(daily, 'blog_result_count', return_value=200):
            chosen, rejected = daily.ranked_review_shortlist([bad, good])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]['title'], good['title'])
        self.assertEqual(len(rejected), 1)

    def test_review_score_is_saved(self):
        candidate = item('생활비 지원 방법')
        candidate['editorial_score'] = es.score(candidate, [candidate], 1000)
        with patch.object(daily, 'notion', return_value={'id': 'new'}) as notion:
            daily.save_review_candidate('2026-11-03', '생활정보팁', 1, candidate, 'run', 'source')
        props = notion.call_args.kwargs['json']['properties']
        self.assertEqual(props['추천 점수']['number'], candidate['editorial_score']['total'])
        self.assertEqual(props['상태']['select']['name'], '보류')
        self.assertIn('실측 아님', props['검증 메모']['rich_text'][0]['text']['content'])

if __name__ == '__main__':
    unittest.main()
