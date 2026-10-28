"""hemaflow demo (演示脚本).

Runs the three core engines over synthetic data and prints:
  1. one patient's full-course timeline
  2. a one-week bed gantt with reverse bookings
  3. tiered blood-count alerts across interval patients

Run:  python3 demo.py
"""
from datetime import date, timedelta

from hemaflow.engine import ADMISSION, ASSESSMENT, DISCHARGE
from hemaflow.synthetic import (
    synthetic_plans, synthetic_blood_counts,
)
from hemaflow.beds import Bed, BedScheduler, BookingRequest
from hemaflow.alerts import (
    AlertThresholds, evaluate_batch, trend_summary,
    LEVEL_RED, LEVEL_YELLOW,
)

TODAY = date(2026, 10, 26)


def main() -> None:
    plans = synthetic_plans(TODAY, n=6)
    print("=" * 64)
    print("1) Treatment timeline - %s  (%s, start %s)"
          % (plans[0].patient_id, plans[0].regimen.name,
             plans[0].start_date))
    print("=" * 64)
    for e in plans[0].build_timeline():
        print(f"  {e.date}  C{e.cycle}  {e.kind:<18} {e.note}")

    print()
    print("=" * 64)
    print("2) Reverse bed booking - week of", TODAY)
    print("=" * 64)
    scheduler = BedScheduler([
        Bed("B07", tags=set()), Bed("B12", tags=set()),
        Bed("B15", tags=set()), Bed("B21", tags={"laminar"}),
    ])
    for plan in plans:
        nxt = plan.next_admission(TODAY - timedelta(days=3))
        if nxt:
            b = scheduler.book(BookingRequest(
                patient_id=plan.patient_id, admit=nxt.date, days=4))
            tag = "locked" if b else "NO BED"
            print(f"  {plan.patient_id}  next admit {nxt.date} -> {tag}")
    print()
    print("  gantt (X=confirmed, o=scheduled, .=free), %s + %dd"
          % (TODAY, 7))
    header = ["bed"] + [(TODAY + timedelta(days=i)).strftime("%m-%d")
                        for i in range(7)]
    print("  " + "  ".join(header))
    for row in scheduler.gantt(TODAY, 7):
        print("  " + "  ".join(row))
    scheduler.confirm(plans[0].patient_id)
    print("  -> %s confirmed admission, bed locked"
          % plans[0].patient_id)

    print()
    print("=" * 64)
    print("3) Interval blood-count alerts (thresholds: default)")
    print("=" * 64)
    alerts = []
    for plan in plans:
        alerts += synthetic_blood_counts(plan)
    for bc, level, reasons in evaluate_batch(alerts, AlertThresholds()):
        if level in (LEVEL_RED, LEVEL_YELLOW):
            print(f"  [{level.upper():6}] {bc.patient_id} {bc.date}"
                  f"  {'; '.join(reasons)}")
    print()
    print("  ANC trend, %s:" % plans[1].patient_id)
    print("   ", trend_summary(synthetic_blood_counts(plans[1])))


if __name__ == "__main__":
    main()
