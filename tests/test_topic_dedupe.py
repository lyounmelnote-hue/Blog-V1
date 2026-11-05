import unittest
from src.topic_dedupe import tokens, canonical_url, duplicate_match, filter_duplicates, historical_rows

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
    def test_bad_url(self):
        self.assertEqual(canonical_url("javascript:alert(1)"),"")
    def test_not_approved_by_dedupe(self):
        fresh,_=filter_duplicates([{"title":"공공안심글꼴 설치 가이드","url":"https://a.example/1"}],[])
        self.assertNotIn("검증 상태",fresh[0])
if __name__=="__main__":unittest.main()
