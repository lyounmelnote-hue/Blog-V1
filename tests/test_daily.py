import unittest
from src.daily import clean,domain,is_official,shortlist,source_check,allocate_ranked,INTENT_SEEDS,DAILY_LIMIT

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

 def test_intent_seeds_cover_categories(self):
  self.assertEqual(len(INTENT_SEEDS),5)
  self.assertTrue(all(len(v)>=2 for v in INTENT_SEEDS.values()))
 def test_flexible_allocation_fills_ten(self):
  pool=[]
  for c in INTENT_SEEDS:
   for n in range(5):
    pool.append((c,{'title':f'{c} 소재 {n}', 'url':f'https://example.com/{c}/{n}',
                    'editorial_score':{'total':100-n}}))
  selected=allocate_ranked(pool,{},set())
  self.assertEqual(len(selected),DAILY_LIMIT)
  self.assertEqual(len(set(x['url'] for _,x in selected)),DAILY_LIMIT)
 def test_partial_day_backfill_and_category_cap(self):
  pool=[('문화',{'title':f'문화 소재 {n}', 'url':f'https://example.com/{n}',
                   'editorial_score':{'total':100-n}}) for n in range(10)]
  selected=allocate_ranked(pool,{'문화':1},set())
  self.assertEqual(len(selected),3)
 def test_no_duplicate_urls(self):
  item={'title':'소재 1','url':'https://example.com/1','editorial_score':{'total':80}}
  self.assertEqual(allocate_ranked([('문화',item)],{}, {'https://example.com/1'}),[])

if __name__=='__main__': unittest.main()
