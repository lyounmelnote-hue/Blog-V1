import unittest
from src.daily import rule_gate, shortlist
from src.prompt_packet import eligible, image_prompts
from src import main

class V34Tests(unittest.TestCase):
    def test_rule_caution_requires_human(self):
        x=rule_gate('문화', {'title':'가을 전시 안내','summary':'전시 일정과 방문 정보'})
        self.assertEqual(x['A'],'주의')
    def test_rule_rejects_sensitive(self):
        self.assertEqual(rule_gate('핫뉴스',{'title':'정치인 논란','summary':'갈등'})['A'],'제외')
    def test_no_ai_api(self):
        with self.assertRaises(RuntimeError): main.generate('x',[],[])
    def test_unapproved_cannot_create_prompt(self):
        page={'properties':{'상태':{'select':{'name':'선택'}},'연결 글':{'relation':[]},'논란도':{'select':{'name':'주의'}},'신빙성':{'select':{'name':'안전'}},'불쾌도':{'select':{'name':'주의'}},'근거 출처':{'relation':[{'id':'x'}]}}}
        self.assertFalse(eligible(page)[0])
    def test_three_images(self):
        self.assertEqual(len(image_prompts('가을 정리','일상')),3)
