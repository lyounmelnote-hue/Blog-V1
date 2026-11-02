import unittest
from src.prompt_packet import image_prompts, prompt, eligible

class PromptPacketTests(unittest.TestCase):
    def test_three_images(self):
        images = image_prompts('가을 산책', '일상')
        self.assertEqual(len(images), 3)
        self.assertIn('16:9', images[0][1])
        self.assertIn('4:3', images[1][1])
        self.assertIn('4:3', images[2][1])
        self.assertTrue(all('텍스트 없음' in p for _, p in images))
        self.assertTrue(all('살구, 아이보리, 연한 베이지, 세이지 그린' in p for _, p in images))
    def test_prompt_has_images(self):
        text = prompt('가을 산책', '일상', '걷기', [('공식자료', 'https://example.org')])
        self.assertIn('이미지 생성 프롬프트 (총 3장', text)
        self.assertIn('https://example.org', text)
    def test_unsafe_rejected(self):
        page={'properties':{'상태':{'select':{'name':'선택'}},'논란도':{'select':{'name':'주의'}},'신빙성':{'select':{'name':'안전'}},'불쾌도':{'select':{'name':'안전'}},'근거 출처':{'relation':[{'id':'1'}]}}}
        self.assertFalse(eligible(page)[0])

if __name__=='__main__': unittest.main()
