"""Unit tests for hemaflow v0.2 (单元测试).

Run:  python3 -m unittest discover -s . -p "test_*.py"
"""
import unittest
from datetime import date, timedelta

from hemaflow.engine import (
    RegimenTemplate, TreatmentPlan, DoseAdjustment,
    ADMISSION, DISCHARGE, NADIR_CHECK, ASSESSMENT,
)
from hemaflow.beds import Bed, BedScheduler, BookingRequest
from hemaflow.alerts import (
    AlertThresholds, BloodCount, evaluate, evaluate_batch, trend_summary,
    LEVEL_NONE, LEVEL_YELLOW, LEVEL_RED,
)
from hemaflow.config import load_rules, load_thresholds

D = date(2026, 11, 2)


class TestEngine(unittest.TestCase):
    def _plan(self, **kw) -> TreatmentPlan:
        reg = RegimenTemplate(name="T", cycles=3, cycle_length_days=21,
                              inpatient_days=4, nadir_days=(7, 12),
                              assessment_after=(2,))
        return TreatmentPlan(patient_id="P1", regimen=reg, start_date=D,
                             **kw)

    def test_timeline_structure(self):
        events = self._plan().build_timeline()
        kinds = [e.kind for e in events]
        self.assertEqual(kinds.count(ADMISSION), 3)
        self.assertEqual(kinds.count(DISCHARGE), 3)
        self.assertEqual(kinds.count(NADIR_CHECK), 6)
        self.assertEqual(kinds.count(ASSESSMENT), 1)
        # sorted by date
        self.assertEqual(events, sorted(events, key=lambda e: e.date))

    def test_cycle_spacing(self):
        events = self._plan().build_timeline()
        c1 = next(e for e in events if e.kind == ADMISSION and e.cycle == 1)
        c2 = next(e for e in events if e.kind == ADMISSION and e.cycle == 2)
        self.assertEqual((c2.date - c1.date).days, 21)

    def test_dose_adjustment_propagates(self):
        plan = self._plan(adjustments=[
            DoseAdjustment(cycle=3, drug="X", ratio=0.75)])
        self.assertEqual(plan.dose_ratio(2), 1.0)
        self.assertAlmostEqual(plan.dose_ratio(3), 0.75)

    def test_next_admission(self):
        plan = self._plan()
        nxt = plan.next_admission(D)
        self.assertEqual(nxt.date, D + timedelta(days=21))

    def test_invalid_regimen_rejected(self):
        reg = RegimenTemplate(name="bad", cycles=1, cycle_length_days=2,
                              inpatient_days=4)
        with self.assertRaises(ValueError):
            TreatmentPlan("P", reg, D).build_timeline()


class TestBeds(unittest.TestCase):
    def setUp(self):
        self.s = BedScheduler([
            Bed("B01"), Bed("B02"), Bed("B21", tags={"laminar"}),
        ])

    def test_book_and_conflict(self):
        req = BookingRequest("P1", D, 4)
        bk = self.s.book(req)
        self.assertIsNotNone(bk)
        # overlapping booking on same bed window must go elsewhere/None
        full = BedScheduler([Bed("B01")])
        full.book(BookingRequest("P1", D, 4))
        self.assertIsNone(full.book(BookingRequest("P2", D + timedelta(days=2), 2)))
        self.assertEqual(len(full.unsatisfied), 1)

    def test_preferred_bed(self):
        self.s.book(BookingRequest("P1", D, 3, preferred_bed="B02"))
        bk2 = self.s.book(BookingRequest(
            "P1", D + timedelta(days=21), 3, preferred_bed="B02"))
        self.assertEqual(bk2.bed_id, "B02")  # same bed as last cycle

    def test_tag_constraint(self):
        bk = self.s.book(BookingRequest("P1", D, 2,
                                        required_tags={"laminar"}))
        self.assertEqual(bk.bed_id, "B21")

    def test_gender_separation(self):
        self.s.book(BookingRequest("Pm", D, 5, gender="male"))
        bk = self.s.book(BookingRequest("Pf", D + timedelta(days=1), 3, gender="female"))
        self.assertNotEqual(bk.bed_id, "B01")  # locked to male occupant

    def test_disinfection_gap(self):
        s = BedScheduler([Bed("B01")], disinfection_days=1)
        s.book(BookingRequest("P1", D, 3))
        bk = s.book(BookingRequest("P2", D + timedelta(days=4), 2))  # needs 1 gap day
        self.assertIsNotNone(bk)                    # D+4 ok (D+3 gap... )
        # exactly adjacent (no gap) must fail on single-bed scheduler
        s2 = BedScheduler([Bed("B01")], disinfection_days=1)
        s2.book(BookingRequest("P1", D, 3))
        self.assertIsNone(s2.book(BookingRequest("P2", D + timedelta(days=3), 2)))


class TestAlerts(unittest.TestCase):
    T = AlertThresholds()

    def test_normal(self):
        bc = BloodCount("P", "2026-01-01", wbc=4.0, anc=2.5, plt=150,
                        hb=120, temperature=36.5)
        self.assertEqual(evaluate(bc, self.T), LEVEL_NONE)

    def test_yellow(self):
        bc = BloodCount("P", "2026-01-01", anc=0.8, plt=100)
        self.assertEqual(evaluate(bc, self.T), LEVEL_YELLOW)

    def test_red_anc(self):
        bc = BloodCount("P", "2026-01-01", anc=0.4, plt=100)
        self.assertEqual(evaluate(bc, self.T), LEVEL_RED)

    def test_red_fever(self):
        bc = BloodCount("P", "2026-01-01", anc=2.0, temperature=38.1)
        self.assertEqual(evaluate(bc, self.T), LEVEL_RED)

    def test_batch_and_reasons(self):
        recs = [BloodCount("P1", "2026-01-01", anc=0.4),
                BloodCount("P2", "2026-01-02", anc=2.0)]
        out = evaluate_batch(recs, self.T)
        self.assertEqual(out[0][1], LEVEL_RED)
        self.assertIn("ANC", out[0][2][0])
        self.assertEqual(out[1][1], LEVEL_NONE)

    def test_trend(self):
        s = trend_summary([BloodCount("P", "2026-01-02", anc=1.0),
                           BloodCount("P", "2026-01-01", anc=2.0)])
        self.assertIn("2026-01-01:2.0 -> 2026-01-02:1.0", s)


class TestConfig(unittest.TestCase):
    def test_load_rules(self):
        rules = load_rules("config/rules.example.json")
        self.assertIn("R-CHOP", rules["regimens"])
        reg = rules["regimens"]["R-CHOP"]
        self.assertEqual(reg.cycle_length_days, 21)
        th = load_thresholds("config/rules.example.json", "high_risk")
        self.assertEqual(th.anc_yellow, 1.5)

    def test_missing_group(self):
        with self.assertRaises(KeyError):
            load_thresholds("config/rules.example.json", "nope")

    def test_invalid_regimen(self):
        import json, tempfile, os
        bad = {"regimens": [{"name": "x"}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as f:
            json.dump(bad, f)
            p = f.name
        try:
            with self.assertRaises(ValueError):
                load_rules(p)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
