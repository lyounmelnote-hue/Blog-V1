import unittest
from src.selected import selection_eligible

class SelectedTest(unittest.TestCase):
    def make(self, state='선택', gate='안전', evidence=True):
        return {'properties':{'상태':{'select':{'name':state}},
                 '논란도':{'select':{'name':gate}},'신빙성':{'select':{'name':'안전'}},
                 '불쾌도':{'select':{'name':'안전'}},
                 '근거 출처':{'relation':[{'id':'source'}] if evidence else []},
                 '후보 제목':{'title':[{'plain_text':'공공 안내'}]}}}
    def test_safe_selected(self): self.assertTrue(selection_eligible(self.make())[0])
    def test_risky_blocked(self): self.assertFalse(selection_eligible(self.make(gate='주의'))[0])
    def test_no_evidence_blocked(self): self.assertFalse(selection_eligible(self.make(evidence=False))[0])
    def test_unselected_blocked(self): self.assertFalse(selection_eligible(self.make(state='추천'))[0])
