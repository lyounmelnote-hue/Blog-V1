import unittest
from unittest.mock import patch
import requests
from datetime import date
from src import performance_review as pr


def rt(s):
    return [{'plain_text': s}]


def content(cid='c1', status='발행 완료', pub='2026-10-20', rec='r1'):
    return {'id':cid,'properties':{
        '제목': {'title':rt('테스트 게시글')},
        '상태': {'select':{'name':status}},
        '실제 발행일': {'date':{'start':pub}} if pub else {'date':None},
        '일일 추천': {'relation':[{'id':rec}]} if rec else {'relation':[]}}}


def rec(rid='r1', score=70):
    return {'id':rid,'properties':{'추천 점수':{'number':score}}}


def measurement(aid='a1', cid='c1', day='2026-10-23', views=100, edit='2026-10-23T09:00:00Z'):
    return {'id':aid,'last_edited_time':edit,'properties':{
        '콘텐츠':{'relation':[{'id':cid}]},
        '측정일':{'date':{'start':day}},
        '조회수':{'number':views},
        '공감 수':{'number':3}, '공유 수':{'number':1}, '댓글 수':{'number':0}}}


class PerformanceReviewTests(unittest.TestCase):
    @patch('src.performance_review.notion')
    @patch('src.performance_review.query')
    def test_analytics_database_id_fallback(self, query, notion):
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError('404', response=response)
        query.side_effect = [error, [{'id': 'measurement-1'}]]
        notion.return_value = {'data_sources': [{'id': 'real-source-id'}]}
        result = pr.fetch_analytics_rows()
        self.assertEqual(result[0]['id'], 'measurement-1')
        self.assertEqual(query.call_args.args[0], 'real-source-id')

    @patch('src.performance_review.notion')
    @patch('src.performance_review.query')
    def test_analytics_permission_error_is_explicit(self, query, notion):
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError('404', response=response)
        query.side_effect = error
        notion.side_effect = error
        with self.assertRaisesRegex(RuntimeError, 'NOTION_TOKEN'):
            pr.fetch_analytics_rows()

    def test_snapshot_not_sum(self):
        summary, rows=pr.report([content()],[
            measurement(day='2026-10-21',views=50),
            measurement(aid='a2',day='2026-10-23',views=120)], [rec()],
            as_of=date(2026,11,3))
        self.assertEqual(rows[0]['views_7d_snapshot'],120)
        self.assertEqual(summary['comparable'],1)

    def test_latest_edit_for_same_day(self):
        rows=[measurement(views=40),measurement(aid='a2',views=90,edit='2026-10-24T09:00:00Z')]
        self.assertEqual(pr.latest_analytics(rows)[('c1',date(2026,10,23))]['id'],'a2')

    def test_not_published_excluded(self):
        summary, rows=pr.report([content(status='REVIEW')],[measurement()],[rec()],as_of=date(2026,11,3))
        self.assertEqual(summary['comparable'],0)
        self.assertIn('미발행',rows[0]['exclusion_reason'])

    def test_immature_article_excluded(self):
        summary, rows=pr.report([content(pub='2026-11-01')],[measurement(day='2026-11-02')],[rec()],as_of=date(2026,11,3))
        self.assertIn('관찰 기간 부족',rows[0]['exclusion_reason'])

    def test_missing_recommendation_excluded(self):
        _, rows=pr.report([content(rec='')],[measurement()],[rec()],as_of=date(2026,11,3))
        self.assertIn('추천 점수',rows[0]['exclusion_reason'])

    def test_missing_views_excluded(self):
        _, rows=pr.report([content()],[],[rec()],as_of=date(2026,11,3))
        self.assertIn('조회수',rows[0]['exclusion_reason'])

    def test_late_snapshot_not_included(self):
        _, rows=pr.report([content()],[measurement(day='2026-10-29')],[rec()],as_of=date(2026,11,3))
        self.assertIsNone(rows[0]['views_7d_snapshot'])

    def test_spearman(self):
        self.assertEqual(pr.spearman([1,2,3,4,5],[10,20,30,40,50]),1.0)
        self.assertEqual(pr.spearman([1,2,3,4,5],[50,40,30,20,10]),-1.0)
        self.assertIsNone(pr.spearman([1,1,1,1,1],[1,2,3,4,5]))

    def test_correlation_threshold(self):
        cs=[content(cid='c'+str(i),rec='r'+str(i)) for i in range(5)]
        rs=[rec('r'+str(i),i+50) for i in range(5)]
        ms=[measurement('a'+str(i),'c'+str(i),views=(i+1)*100) for i in range(5)]
        summary,_=pr.report(cs,ms,rs,as_of=date(2026,11,3))
        self.assertEqual(summary['spearman_score_vs_views'],1.0)

    def test_negative_or_invalid_metric_ignored(self):
        row=measurement(views=-2)
        self.assertIsNone(pr.number(row,'조회수'))

if __name__=='__main__':
    unittest.main()
