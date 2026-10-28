"""Reverse bed scheduler (反向排床调度器).

Beds are modelled as resources over a date range. The scheduler takes
scheduled admissions produced by the cycle engine and reserves beds in
advance ("reverse booking"), detecting conflicts such as a bed that is
still occupied on the requested date.

Greedy first-fit assignment; intentionally simple so clinicians can
audit every decision. Constraints like airflow/isolation bed types are
modelled with ``bed_tags``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set


@dataclass
class Bed:
    bed_id: str
    tags: Set[str] = field(default_factory=set)  # e.g. {"laminar"}
    gender: Optional[str] = None                 # "male"/"female"/None(不限)


@dataclass
class Booking:
    bed_id: str
    patient_id: str
    admit: date
    days: int
    status: str = "scheduled"  # scheduled / confirmed / cancelled
    note: str = ""
    gender: Optional[str] = None


@dataclass
class BookingRequest:
    """An admission request to satisfy (一次入院请求).

    ``required_tags`` lists bed tags that must all be present, e.g.
    ``{"laminar"}`` for a febrile neutropenia readmission.
    ``gender`` enables male/female ward separation (男女分区).
    """

    patient_id: str
    admit: date
    days: int
    required_tags: Set[str] = field(default_factory=set)
    preferred_bed: Optional[str] = None  # keep same bed as last cycle
    gender: Optional[str] = None
    priority: int = 0  # larger = more urgent (e.g. febrile neutropenia)


class BedScheduler:
    """First-fit bed allocation over a date window (床位甘特/锁床).

    Constraints supported (v0.2):
      - bed tags (required_tags ⊆ bed.tags)
      - gender separation (男女分区): a bed's gender locks to the
        occupant; mixed-gender booking on one bed is rejected
      - disinfection gap: ``disinfection_days`` free between two
        consecutive patients on the same bed (消毒间隔)
    """

    def __init__(self, beds: List[Bed], disinfection_days: int = 0):
        self.beds = {b.bed_id: b for b in beds}
        self.bookings: List[Booking] = []
        self.unsatisfied: List[BookingRequest] = []
        self.disinfection_days = int(disinfection_days)

    # ------------------------------------------------------------- helpers
    def _occupied(self, bed_id: str, start: date, days: int) -> bool:
        """True if [start, start+days) conflicts with any booking on the
        bed, honouring the disinfection gap between consecutive patients
        (同床消毒间隔): two stays must satisfy
        ``new_end + gap <= old_start`` or ``old_end + gap <= new_start``.
        """
        gap = self.disinfection_days
        n0 = start.toordinal()
        n1 = n0 + days
        for bk in self.bookings:
            if bk.bed_id != bed_id or bk.status == "cancelled":
                continue
            b0 = bk.admit.toordinal()
            b1 = b0 + bk.days
            if not (n1 + gap <= b0 or b1 + gap <= n0):
                return True
        return False

    def _bed_matches(self, bed: Bed, req: BookingRequest) -> bool:
        if not req.required_tags.issubset(bed.tags):
            return False
        if req.gender and bed.gender and req.gender != bed.gender:
            return False
        # gender separation: an occupied bed keeps its occupant's gender
        for bk in self.bookings:
            if (bk.bed_id == bed.bed_id and bk.status != "cancelled"
                    and bk.gender and req.gender
                    and bk.gender != req.gender):
                return False
        return True

    # -------------------------------------------------------------- public
    def book(self, req: BookingRequest) -> Optional[Booking]:
        """Try to reserve a bed; returns Booking or None (预约锁床)."""
        order = list(self.beds.values())
        if req.preferred_bed and req.preferred_bed in self.beds:
            pref = self.beds[req.preferred_bed]
            if self._bed_matches(pref, req):
                order.sort(key=lambda b: b.bed_id != pref.bed_id)
        for bed in order:
            if not self._bed_matches(bed, req):
                continue
            if self._occupied(bed.bed_id, req.admit, req.days):
                continue
            booking = Booking(
                bed_id=bed.bed_id,
                patient_id=req.patient_id,
                admit=req.admit,
                days=req.days,
                status="scheduled",
                gender=req.gender or None,
                note=("priority=%d" % req.priority) if req.priority else "",
            )
            self.bookings.append(booking)
            return booking
        self.unsatisfied.append(req)
        return None

    def confirm(self, patient_id: str) -> bool:
        """Patient confirmed admission (患者端确认 -> 锁床生效)."""
        for bk in reversed(self.bookings):
            if bk.patient_id == patient_id and bk.status == "scheduled":
                bk.status = "confirmed"
                return True
        return False

    def conflicts_on(self, day: date) -> List[str]:
        """Human-readable conflict notes for the day (当日冲突提醒)."""
        notes = []
        occupied = {
            bk.bed_id for bk in self.bookings
            if bk.status != "cancelled"
            and bk.admit.toordinal() <= day.toordinal()
            < bk.admit.toordinal() + bk.days
        }
        for bk in self.bookings:
            if bk.status in ("scheduled", "confirmed") and bk.admit == day:
                if bk.bed_id in occupied - {
                    b.bed_id for b in self.bookings
                    if b.patient_id == bk.patient_id
                }:
                    pass  # overlap already prevented by _occupied
        free = set(self.beds) - occupied
        due = [bk for bk in self.bookings if bk.admit == day
               and bk.status != "cancelled"]
        if len(due) > len(free) + len(occupied):
            notes.append("admissions exceed capacity")  # defensive
        for bk in due:
            notes.append(
                f"{bk.admit} bed {bk.bed_id}: {bk.patient_id} "
                f"admits for {bk.days}d ({bk.status})"
            )
        return notes

    def gantt(self, start: date, days: int) -> List[List[str]]:
        """Simple text gantt: rows = beds, cols = days (文本甘特图)."""
        grid = []
        for bed in self.beds.values():
            row = [bed.bed_id]
            for i in range(days):
                d = date.fromordinal(start.toordinal() + i)
                cell = "."
                for bk in self.bookings:
                    if bk.bed_id != bed.bed_id or bk.status == "cancelled":
                        continue
                    if bk.admit.toordinal() <= d.toordinal() < (
                        bk.admit.toordinal() + bk.days
                    ):
                        cell = "X" if bk.status == "confirmed" else "o"
                row.append(cell)
            grid.append(row)
        return grid
