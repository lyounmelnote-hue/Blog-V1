import unittest
from unittest.mock import patch
from src import daily

class ReviewQueueTests(unittest.TestCase):
    def test_only_safe_looking_items_queued(self):
        items=[{'title':'공공 생활 정보 안내','summary':'생활에 필요한 공공 정보입니다','url':'https://example.com/a'},
               {'title':'선거 관련 안내','summary':'정치 소식','url':'https://example.com/b'},
               {'title':'출처 없는 정보','summary':'생활 안내','url':''}]
        accepted,rejected=daily.queue_shortlist(items)
        self.assertEqual(len(accepted),1)
        self.assertEqual(len(rejected),2)
    def test_unverified_source_payload(self):
        item={'title':'문화 행사 정보','summary':'행사 일정','url':'https://example.com/a'}
        with patch.object(daily,'notion',return_value={'id':'source-id'}) as api:
            daily.create_unverified_source(item)
            p=api.call_args.kwargs['json']['properties']
            self.assertEqual(p['검증 상태']['select']['name'],'UNVERIFIED')
            self.assertFalse(p['원문 확인 여부']['checkbox'])
    def test_candidate_never_auto_safe(self):
        item={'title':'문화 행사 정보','summary':'행사 일정','url':'https://example.com/a'}
        with patch.object(daily,'notion',return_value={'id':'page-id'}) as api:
            daily.save_review_candidate('2026-11-02','문화',1,item,'run','source-id')
            p=api.call_args.kwargs['json']['properties']
            self.assertEqual(p['상태']['select']['name'],'보류')
            for k in ('논란도','신빙성','불쾌도'):
                self.assertEqual(p[k]['select']['name'],'주의')
