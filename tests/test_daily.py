import unittest
from src.daily import clean,domain,is_official,shortlist,source_check

class DailyTests(unittest.TestCase):
 def test_clean(self): self.assertEqual(clean('<b>문화</b> &amp; 행사'),'문화 & 행사')
 def test_domain(self): self.assertEqual(domain('https://www.kdca.go.kr/a'),'kdca.go.kr')
 def test_official(self):
  self.assertTrue(is_official('https://www.kdca.go.kr'))
  self.assertFalse(is_official('https://kdca.go.kr.evil.com'))
 def test_no_evidence(self):
  self.assertFalse(source_check('건강',{'title':'예방 건강 수칙'},[])[0])
 def test_blocked(self):
  item={'title':'선거 관련 갈등','summary':'내용','url':'https://example.com'}
  good={'id':'1','title':'선거 관련 갈등','evidence':'선거 관련 갈등','url':'https://kdca.go.kr'}
  a,b=shortlist('문화',[item],[good],judge=lambda *_:{'A':'안전','C':'안전'})
  self.assertEqual(len(a),0)
 def test_gate_caution(self):
  item={'title':'계절 건강 수칙','summary':'예방 수칙','url':'https://example.com'}
  good={'id':'1','title':'계절 건강 수칙','evidence':'계절 건강 수칙','url':'https://kdca.go.kr'}
  a,b=shortlist('건강',[item],[good],judge=lambda *_:{'A':'안전','C':'주의'})
  self.assertEqual(len(a),0)

if __name__=='__main__': unittest.main()
