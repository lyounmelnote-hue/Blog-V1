import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch

from src import category_fit, daily, editorial_score
from src.naver_cache import SearchCache


class CategoryTests(unittest.TestCase):
    def test_all_categories_require_title_summary_and_intent(self):
        examples = {
            '문화': ('박물관 전시 관람 예약', '전시 일정과 입장 비용 안내'),
            '일상': ('가을 산책 루틴 추천', '계절 산책 코스 준비 방법'),
            '생활정보팁': ('주거 지원금 신청 방법', '주택 지원금 대상 조건 안내'),
            '건강': ('고혈압 예방 관리 방법', '고혈압 검진 대상과 건강 수칙'),
            '핫뉴스': ('우주 연구 기술 발표', '연구 결과와 기술 변경 영향 안내'),
        }
        for category, (title, summary) in examples.items():
            with self.subTest(category=category):
                self.assertTrue(category_fit.evaluate(category, dict(title=title, summary=summary))['accepted'])
                self.assertFalse(category_fit.evaluate(category, dict(title='기업 소식 안내', summary=summary))['accepted'])
                self.assertFalse(category_fit.evaluate(category, dict(title=title, summary='새로운 소식입니다'))['accepted'])

    def test_health_rejects_policy_despite_incidental_health_words(self):
        for title in ('건강한 주거 위한 청약 지원 안내', '대출 금리 변경 건강한 경제', '주택 분양 지원금 신청'):
            fit = category_fit.evaluate('건강', {'title': title, 'summary': '보건복지부 건강 예방 안내와 지원 대상'})
            self.assertFalse(fit['accepted'])
            self.assertIn('주거·경제', fit['reason'])
        self.assertTrue(category_fit.evaluate('건강', {'title': '건강 검진 지원 확대', 'summary': '건강 검진 신청 대상과 예방 수칙 안내'})['accepted'])

    def test_reader_intent_is_required(self):
        self.assertFalse(category_fit.evaluate('문화', {'title': '문화 기업 소식', 'summary': '문화 기업 임직원 모임'})['accepted'])

    def test_hot_news_distinguishes_public_change_from_personal_howto(self):
        for title, summary in (
            ('휴대폰 요금제 변경 전 확인할 6가지', '요금제 변경 방법과 할인 조건 안내'),
            ('2027 유치원 입학 준비 모집 일정과 유아학비 변경신청', '교육 제도 변경 신청 안내'),
            ('2027학년도 과학기술원 정시 일정', '과학기술원 입학 제도 발표')):
            self.assertFalse(category_fit.evaluate('핫뉴스', dict(title=title, summary=summary))['accepted'])
        self.assertTrue(category_fit.evaluate('핫뉴스', {'title': '난임치료휴가 유급 확대 시행', 'summary': '휴가 제도 변경 대상과 시행 일정 안내'})['accepted'])

    def test_health_includes_infection_but_excludes_career_intent(self):
        self.assertTrue(category_fit.evaluate('건강', {'title': '독감 유행 예방 수칙', 'summary': '독감 백신 접종 대상과 예방 안내'})['accepted'])
        self.assertFalse(category_fit.evaluate('건강', {'title': '건강관리사 자격증 교육기관 안내', 'summary': '건강 관리 방법과 교육 과정 안내'})['accepted'])

    def test_practical_information_beats_advertising_and_event_notice(self):
        guide = {'title': '전시 관람 예약 방법 비교', 'summary': '전시 일정 비용과 대상 조건 준비 안내'}
        for title in ('기업 홍보 브랜드 론칭 광고', '행사 개최 발표 기념식 성료', '업무협약 수상 보도자료'):
            self.assertGreater(editorial_score.blog_fit(guide), editorial_score.blog_fit({'title': title, 'summary': '새로운 소식을 발표했다'}))


class CacheTests(unittest.TestCase):
    def test_duplicate_queries_and_collection_total_reuse(self):
        cache = SearchCache()
        request = Mock(return_value={'items': [], 'total': 300})
        cache.get(request, 'news', '건강  예방', 8, {})
        cache.get(request, 'news', '건강 예방', 8, {})
        cache.get(request, 'blog', '건강 예방', 8, {})
        self.assertEqual(cache.get(request, 'blog', '건강 예방', 1, {})['total'], 300)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(cache.report()['cache_hits'], {'news': 1, 'blog_total': 1})
        cache.get(request, 'news', '건강 예방', 10, {})
        self.assertEqual(request.call_count, 3)

    def test_errors_not_cached_and_new_run_is_fresh(self):
        request = Mock(side_effect=[RuntimeError('temporary'), {'total': 10}, {'total': 20}])
        cache = SearchCache()
        with self.assertRaises(RuntimeError):
            cache.get(request, 'blog', '검색어', 1, {})
        self.assertEqual(cache.get(request, 'blog', '검색어', 1, {})['total'], 10)
        self.assertEqual(SearchCache().get(request, 'blog', '검색어', 1, {})['total'], 20)

    def test_same_scoring_phrase_is_looked_up_once(self):
        items = [{'title': '전시 관람 예약 방법 ' + str(i), 'url': str(i)} for i in range(3)]
        lookup = Mock(return_value=100)
        editorial_score.rank(items, lookup, top=3)
        self.assertEqual(lookup.call_count, 1)


class PipelineTests(unittest.TestCase):
    def test_capacity_boundaries_and_rejections_before_api(self):
        for existing in (0, 6, 9, 10):
            with self.subTest(existing=existing):
                rows = [{'id': str(i), 'properties': {'분야': {'select': {'name': '문화'}}}} for i in range(existing)]
                candidates = [
                    {'title': '박물관 전시 예약 방법 ' + str(100 + i),
                     'summary': '전시 관람 일정 비용 조건 준비 안내',
                     'url': f'https://example.org/{i}', 'published_at': daily.date_kst()}
                    for i in range(12)]
                bad = {'title': '주택 청약 신청 안내', 'summary': '건강한 주거 지원 대상', 'url': 'https://example.org/bad'}
                out = io.StringIO()
                with patch.dict('os.environ', {'DRY_RUN': 'true', 'REVIEW_QUEUE': 'true'}), \
                     patch.object(daily, 'existing_day_rows', return_value=rows), \
                     patch.object(daily.topic_dedupe, 'historical_rows', return_value=[]), \
                     patch.object(daily, 'collect_candidates', side_effect=lambda c: candidates if c == '문화' else [bad] if c == '건강' else []), \
                     patch.object(daily, 'blog_result_count', return_value=1000) as lookup, \
                     patch.object(daily, 'notion') as writer, contextlib.redirect_stdout(out):
                    daily.run()
                writer.assert_not_called()
                selected = [json.loads(line.partition(' ')[2]) for line in out.getvalue().splitlines() if line.startswith('RECOMMENDATION ')]
                self.assertEqual(len(selected), 10 - existing)
                self.assertTrue(all(x['score'] >= 55 and not x['duplicate'] for x in selected))
                if existing == 10:
                    lookup.assert_not_called()
                else:
                    self.assertIn('CATEGORY:', out.getvalue())
                    self.assertNotIn('주택', ' '.join(x['title'] for x in selected))


if __name__ == '__main__':
    unittest.main()
