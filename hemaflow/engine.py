"""Treatment cycle engine (周期引擎).

Generates a full-course treatment timeline from a regimen template:
per-cycle admission / chemo / discharge dates, interval monitoring
checkpoints and mid-course assessment nodes. Dose adjustments can be
propagated to subsequent cycles.

All dates are plain ``datetime.date`` objects. The engine is pure logic:
no I/O, no database, easy to embed and to test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

# ---------------------------------------------------------------- events

ADMISSION = "admission"          # 入院日
CHEMO = "chemo"                  # 化疗用药日
DISCHARGE = "discharge"          # 预计出院日
NADIR_CHECK = "nadir_check"      # 间隔期血象复查(低谷期)
DISCHARGE_SUMMARY = "discharge_summary"  # 出院小结推送
ASSESSMENT = "assessment"        # 中期疗效评估


@dataclass
class TimelineEvent:
    """A single dated event on the patient timeline (时间轴事件)."""

    date: date
    kind: str
    cycle: int
    note: str = ""


@dataclass
class RegimenTemplate:
    """Chemo regimen template (方案模板), e.g. R-CHOP 21d x6.

    cycle_length_days: interval between cycle start days (21/28/...)
    inpatient_days:    admission -> discharge length
    nadir_days:        interval days on which blood counts are uploaded
    assessment_after:  cycle numbers after which an assessment is due
    """

    name: str
    cycles: int = 6
    cycle_length_days: int = 21
    inpatient_days: int = 4
    nadir_days: tuple = (7, 12)
    assessment_after: tuple = (2, 4, 6)
    drugs: tuple = ()

    def validate(self) -> None:
        if self.cycle_length_days < self.inpatient_days + 1:
            raise ValueError("cycle_length_days must exceed inpatient_days")


@dataclass
class DoseAdjustment:
    """Dose adjustment applied during one cycle (剂量调整).

    ratio < 1.0 (e.g. 0.75) and ``propagate=True`` will carry the ratio
    into all subsequent cycles, mirroring the common clinical practice
    of reducing anthracycline dose after severe neutropenia.
    """

    cycle: int
    drug: str
    ratio: float
    reason: str = ""
    propagate: bool = True


@dataclass
class TreatmentPlan:
    """Full-course plan of one patient (患者全疗程计划)."""

    patient_id: str
    regimen: RegimenTemplate
    start_date: date
    adjustments: List[DoseAdjustment] = field(default_factory=list)

    def dose_ratio(self, cycle: int) -> float:
        ratio = 1.0
        for adj in self.adjustments:
            if adj.propagate and adj.cycle <= cycle:
                ratio *= adj.ratio
        return ratio

    # ------------------------------------------------------------- engine
    def build_timeline(self) -> List[TimelineEvent]:
        """Generate all timeline events (生成全疗程时间轴)."""
        self.regimen.validate()
        events: List[TimelineEvent] = []
        for c in range(1, self.regimen.cycles + 1):
            cycle_start = self.start_date + timedelta(
                days=(c - 1) * self.regimen.cycle_length_days
            )
            events.append(TimelineEvent(cycle_start, ADMISSION, c))
            events.append(
                TimelineEvent(cycle_start, CHEMO, c, note="chemo day 1")
            )
            discharge = cycle_start + timedelta(
                days=self.regimen.inpatient_days - 1
            )
            events.append(TimelineEvent(discharge, DISCHARGE, c))
            events.append(TimelineEvent(discharge, DISCHARGE_SUMMARY, c))
            for d in self.regimen.nadir_days:
                events.append(
                    TimelineEvent(
                        cycle_start + timedelta(days=d),
                        NADIR_CHECK,
                        c,
                        note=f"interval day {d}",
                    )
                )
            if c in self.regimen.assessment_after:
                events.append(
                    TimelineEvent(
                        discharge + timedelta(days=1),
                        ASSESSMENT,
                        c,
                        note=f"post-cycle-{c} assessment",
                    )
                )
        events.sort(key=lambda e: (e.date, e.cycle))
        return events

    def next_admission(self, today: date) -> Optional[TimelineEvent]:
        """First scheduled admission strictly after ``today`` (下次入院)."""
        for e in self.build_timeline():
            if e.kind == ADMISSION and e.date > today:
                return e
        return None
