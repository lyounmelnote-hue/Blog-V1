import unittest
from src.quality_review import score_draft

class QualityReviewTests(unittest.TestCase):
    def test_empty_draft_is_not_approvable(self):
        r = score_draft("")
        self.assertFalse(r["approval_eligible"])
        self.assertLess(r["score"], 85)
    def test_good_structure_still_requires_human(self):
        body = ("## 소개\n" + "사무실 문서 정리 방법입니다. " * 70 +
                "\n## 방법\n자료를 구분합니다.\n## 점검\n보관 기준을 확인합니다.\n"
                "https://www.notion.so/help\n#문서정리")
        r = score_draft(body)
        self.assertFalse(r["approval_eligible"])
        self.assertIn("차별성", r["checks"])
        self.assertEqual(r["checks"]["차별성"], 0)
    def test_no_source_blocker(self):
        r = score_draft("## 제목\n" + "문서 관리 " * 150)
        self.assertIn("참고 출처 URL 없음", r["blockers"])
if __name__ == "__main__":
    unittest.main()
