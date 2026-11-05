import unittest
from src.topic_dedupe import tokens, canonical_url, duplicate_match, filter_duplicates, historical_rows, semantic_topic_match

def row(title,url="https://news.example/a",day="2026-11-04"):
    return {"id":"prior-1","properties":{"후보 제목":{"title":[{"plain_text":title}]},"원본 링크":{"url":url},"추천일":{"date":{"start":day}}}}

class TopicDedupeTests(unittest.TestCase):
    def test_same_url_tracking_stripped(self):
        self.assertEqual(duplicate_match({"title":"다른 제목","url":"https://news.example/a?utm_source=foo"},[row("원제목")])["type"],"URL")
    def test_same_topic_reordered(self):
        self.assertEqual(duplicate_match({"title":"다자녀 가구 지원 지역별 차이","url":"https://else.example/b"},[row("지역별 다자녀 가구 지원 차이")])["type"],"TOPIC")
    def test_single_shared_keyword_not_duplicate(self):
        self.assertIsNone(duplicate_match({"title":"정부24 전입신고 방법","url":"https://else.example/b"},[row("정부24 주민등록등본 발급 방법")]))
    def test_changed_topic_not_suppressed(self):
        self.assertIsNone(duplicate_match({"title":"다자녀 지원금 신청 절차 변경","url":"https://else.example/b"},[row("다자녀 가구 지원 지역별 차이")]))
    def test_filter_keeps_novel(self):
        fresh,duplicates=filter_duplicates([{"title":"지역별 다자녀 가구 지원 차이","url":"https://else.example/b"},{"title":"공공안심글꼴 설치 가이드","url":"https://else.example/c"}],[row("다자녀 가구 지원 지역별 차이")])
        self.assertEqual((len(fresh),len(duplicates)),(1,1))
    def test_within_batch(self):
        fresh,duplicates=filter_duplicates([{"title":"공공안심글꼴 설치 가이드","url":"https://a.example/1"},{"title":"설치 공공안심글꼴 가이드","url":"https://b.example/2"}],[])
        self.assertEqual((len(fresh),len(duplicates)),(1,1))
    def test_exact_seven_day_range(self):
        calls=[]
        def query(ds,flt,page_size):
            calls.append(flt);return []
        historical_rows(query,"DS","2026-11-05")
        self.assertEqual(calls[0]["and"][0]["date"]["on_or_after"],"2026-10-29")
        self.assertEqual(calls[0]["and"][1]["date"]["before"],"2026-11-05")
    def test_semantic_same_policy_different_headline(self):
        self.assertTrue(semantic_topic_match(
            "고혈압 당뇨 관리 전국 확대 통합센터 운영",
            "고혈압 당뇨 관리 확대 전국 통합센터 시행"))
    def test_distinct_guides_with_shared_keyword(self):
        self.assertFalse(semantic_topic_match(
            "정부24 주민등록등본 발급 방법 정리",
            "정부24 전입신고 신청 방법 안내"))
    def test_blog_fit_rewards_howto(self):
        from src.editorial_score import blog_fit
        self.assertGreater(blog_fit({'title':'난방비 절약 보일러 사용법 정리'}),
                           blog_fit({'title':'지역 기념식 축사 기념행사 성료'}))
    def test_bad_url(self):
        self.assertEqual(canonical_url("javascript:alert(1)"),"")
    def test_not_approved_by_dedupe(self):
        fresh,_=filter_duplicates([{"title":"공공안심글꼴 설치 가이드","url":"https://a.example/1"}],[])
        self.assertNotIn("검증 상태",fresh[0])

class IntegrationAllocationTests(unittest.TestCase):
    def test_partial_backfill_and_capacity(self):
        from src.daily import choose_flexible, CATEGORIES
        def item(n):
            return {'title': str(n), 'editorial_score': {'total': 90-n}}
        pool={c:[item(i) for i in range(5)] for c in CATEGORIES}
        result=choose_flexible(pool, {'문화':1,'일상':2})
        self.assertEqual(len(result),7)
        self.assertEqual(sum(c=='문화' for c,_ in result)>=1,True)
    def test_flexible_fills_from_other_categories(self):
        from src.daily import choose_flexible, CATEGORIES
        pool={c:[] for c in CATEGORIES}
        pool['문화']=[{'title':str(i),'editorial_score':{'total':90-i}} for i in range(12)]
        result=choose_flexible(pool,{})
        self.assertEqual(len(result),10)
    def test_collects_news_and_blog(self):
        from unittest.mock import patch
        from src.daily import collect_candidates, SEEDS
        with patch('src.daily.search',side_effect=lambda seed, endpoint, count:[{'title':endpoint,'summary':'text','url':'https://example.com/'+endpoint}]) as mock:
            result=collect_candidates('문화')
        self.assertEqual(len(result),len(SEEDS['문화'])*2)
        self.assertEqual({x['search_endpoint'] for x in result},{'news','blog'})
    def test_blog_postdate_is_used_for_freshness(self):
        from unittest.mock import patch
        from src.daily import search
        payload = {'items': [{'title': '생활정보 정리', 'description': '안내',
                              'link': 'https://blog.example/post', 'postdate': '20261105'}]}
        with patch('src.daily.request', return_value=payload), \
             patch.dict('os.environ', {'NAVER_CLIENT_ID': 'test', 'NAVER_CLIENT_SECRET': 'test'}):
            items = search('생활정보', 'blog')
        self.assertEqual(items[0]['published_at'], '2026-11-05')

    def test_run_dry_does_not_write(self):
        from unittest.mock import patch
        from src import daily
        with patch.dict('os.environ',{'DRY_RUN':'true','REVIEW_QUEUE':'true'}), \
             patch.object(daily,'existing_day_rows',return_value=[]), \
             patch.object(daily.topic_dedupe,'historical_rows',return_value=[]), \
             patch.object(daily,'collect_candidates',return_value=[]), \
             patch.object(daily,'save_log') as log, \
             patch.object(daily,'create_unverified_source') as source, \
             patch.object(daily,'save_review_candidate') as save:
            daily.run()
            log.assert_not_called()
            source.assert_not_called()
            save.assert_not_called()

if __name__=="__main__":unittest.main()
