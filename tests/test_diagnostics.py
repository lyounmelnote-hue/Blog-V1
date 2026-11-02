import unittest
from src.daily import rejection_report, source_report

class DiagnosticTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(rejection_report([]), {})
    def test_counts(self):
        rejected = [({}, 'A: 금지 사전'), ({}, 'B: 근거 없음'), ({}, 'B: 근거 없음'), ({}, 'A/C: 위험 표현')]
        self.assertEqual(rejection_report(rejected), {'A': 1, 'A/C': 1, 'B': 2})
    def test_source_report(self):
        self.assertEqual(source_report([{'url':'https://www.kdca.go.kr/a'}, {'url':'https://example.com'}]), {'verified_usable_sources': 2, 'official_usable_sources': 1})

if __name__ == '__main__':
    unittest.main()
