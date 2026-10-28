"""Tiered blood-count alert engine (分级预警规则引擎).

Pure rule evaluation over lab values. Thresholds are configurable per
regimen / risk group; defaults follow a common conservative starting
point (NOT a medical recommendation):

    yellow: ANC < 1.0e9/L
    red:    ANC < 0.5e9/L  OR  temperature >= 38.0 C
    red:    PLT < 30e9/L   (bleeding risk, also red)

The engine never makes clinical decisions; it only computes a level so
the host system can notify the right people and keep an audit trail.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

LEVEL_NONE = "none"
LEVEL_YELLOW = "yellow"
LEVEL_RED = "red"

_LEVEL_ORDER = {LEVEL_NONE: 0, LEVEL_YELLOW: 1, LEVEL_RED: 2}


@dataclass
class AlertThresholds:
    """Configurable thresholds (阈值集, per regimen/risk group)."""

    anc_yellow: float = 1.0
    anc_red: float = 0.5
    plt_red: float = 30.0
    fever_celsius: float = 38.0


@dataclass
class BloodCount:
    """One lab record (一次血常规), counts in 10^9/L units."""

    patient_id: str
    date: str                      # ISO date string, e.g. "2026-10-25"
    wbc: Optional[float] = None    # 10^9/L
    anc: Optional[float] = None    # 10^9/L
    plt: Optional[float] = None    # 10^9/L
    hb: Optional[float] = None     # g/L
    temperature: Optional[float] = None  # Celsius

    def reasons(self, t: AlertThresholds) -> List[str]:
        r: List[str] = []
        if self.anc is not None and self.anc < t.anc_yellow:
            r.append(f"ANC {self.anc:.2f} < {t.anc_yellow:.1f} x10^9/L")
        if self.plt is not None and self.plt < t.plt_red:
            r.append(f"PLT {self.plt:.0f} < {t.plt_red:.0f} x10^9/L "
                     "bleeding risk")
        if self.temperature is not None and self.temperature >= t.fever_celsius:
            r.append(f"fever {self.temperature:.1f}C")
        return r


def evaluate(bc: BloodCount, t: Optional[AlertThresholds] = None) -> str:
    """Return alert level: none / yellow / red (分级结果)."""
    t = t or AlertThresholds()
    level = LEVEL_NONE
    if bc.anc is not None and bc.anc < t.anc_yellow:
        level = LEVEL_YELLOW
    if bc.anc is not None and bc.anc < t.anc_red:
        level = LEVEL_RED
    if bc.plt is not None and bc.plt < t.plt_red:
        level = LEVEL_RED
    if bc.temperature is not None and bc.temperature >= t.fever_celsius:
        level = LEVEL_RED
    return level


def evaluate_batch(records: List[BloodCount],
                   t: Optional[AlertThresholds] = None) -> List[tuple]:
    """Evaluate many records; returns (record, level, reasons)."""
    t = t or AlertThresholds()
    out = []
    for bc in records:
        level = evaluate(bc, t)
        out.append((bc, level, bc.reasons(t) if level != LEVEL_NONE else []))
    return out


def trend_summary(records: List[BloodCount]) -> str:
    """One-line trend of ANC across records (ANC 趋势摘要)."""
    pts = [(r.date, r.anc) for r in records if r.anc is not None]
    pts.sort()
    return " -> ".join(f"{d}:{a:.1f}" for d, a in pts)
