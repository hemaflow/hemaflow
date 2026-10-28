"""Synthetic demo data generator (合成演示数据生成器).

All data is fully synthetic - deterministic pseudo-random generation
from a fixed seed. No real patient data is ever used in this project.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .engine import RegimenTemplate, TreatmentPlan, DoseAdjustment
from .alerts import BloodCount

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨"
FIRST = ("某某", "阿姨", "叔叔", "大姐", "大爷")


def synthetic_regimens() -> dict:
    return {
        "R-CHOP": RegimenTemplate(
            name="R-CHOP", cycles=6, cycle_length_days=21,
            inpatient_days=4, nadir_days=(7, 12),
            assessment_after=(2, 4, 6),
            drugs=("Rituximab", "Cyclophosphamide", "Doxorubicin",
                   "Vincristine", "Prednisone"),
        ),
        "R2": RegimenTemplate(
            name="R2-len", cycles=6, cycle_length_days=28,
            inpatient_days=2, nadir_days=(10, 21),
            assessment_after=(3, 6),
            drugs=("Rituximab", "Lenalidomide"),
        ),
    }


def synthetic_plans(start: date, n: int = 6, seed: int = 42) -> list:
    rng = random.Random(seed)
    regimens = synthetic_regimens()
    keys = list(regimens)
    plans = []
    for i in range(n):
        reg = regimens[keys[i % len(keys)]]
        start_i = start + timedelta(days=rng.randint(-30, 14))
        plan = TreatmentPlan(
            patient_id=f"P{i:03d}-{SURNAMES[i % len(SURNAMES)]}某某",
            regimen=reg, start_date=start_i,
        )
        # give ~1/3 of patients a propagated dose reduction at C3
        if i % 3 == 1:
            plan.adjustments.append(DoseAdjustment(
                cycle=3, drug="Doxorubicin", ratio=0.75,
                reason="C2 interval ANC nadir 0.6", propagate=True,
            ))
        plans.append(plan)
    return plans


def synthetic_blood_counts(plan: TreatmentPlan, seed: int | None = None
                           ) -> list:
    """Generate interval-period counts with a realistic ANC dip."""
    rng = random.Random(seed or (hash(plan.patient_id) % (2**31)))
    records = []
    base_anc = rng.uniform(1.8, 3.2)
    for c in range(1, plan.regimen.cycles + 1):
        cycle_start = plan.start_date + timedelta(
            days=(c - 1) * plan.regimen.cycle_length_days)
        for d in plan.regimen.nadir_days:
            day = cycle_start + timedelta(days=d)
            dip = rng.uniform(0.30, 0.60) if d <= 12 else rng.uniform(0.55, 0.95)
            anc = max(0.2, base_anc * dip)
            # most interval days are afebrile; ~12% fever (合成数据)
            temp = (round(rng.uniform(38.0, 39.0), 1)
                    if rng.random() < 0.12
                    else round(rng.uniform(36.2, 37.6), 1))
            records.append(BloodCount(
                patient_id=plan.patient_id, date=day.isoformat(),
                wbc=round(anc + rng.uniform(0.5, 1.5), 1),
                anc=round(anc, 2),
                plt=round(rng.uniform(40, 220)),
                hb=round(rng.uniform(85, 130)),
                temperature=temp,
            ))
    return records
