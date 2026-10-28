"""Generate article figures from the HemaFlow engine (文章配图生成).

图1: 一名 R-CHOP 患者 4-5 个月的床位占用时间轴（周期锁死效应）
图2: 病区一周甘特对比：无预约 vs 反向排床锁床

Usage: python3 make_figures.py   (outputs to ../开源内容-配图/)
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import date, timedelta

from hemaflow.engine import RegimenTemplate, TreatmentPlan
from hemaflow.synthetic import synthetic_plans
from hemaflow.beds import Bed, BedScheduler, BookingRequest

# ---- CJK font ----
CJK = None
for f in fm.fontManager.ttflist:
    if "CJK" in f.name or "Noto Sans SC" in f.name or "WenQuanYi" in f.name:
        CJK = f.name
        break
if CJK:
    plt.rcParams["font.family"] = CJK
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.join(os.path.dirname(__file__), "..", "开源内容-配图")
os.makedirs(OUT, exist_ok=True)

BLUE, ORANGE, RED, GRAY = "#1a6fb5", "#f5a623", "#e5484d", "#c3cad4"

# ------------------------------------------------------------- figure 1
reg = RegimenTemplate(name="R-CHOP", cycles=6, cycle_length_days=21,
                      inpatient_days=4, nadir_days=(7, 12),
                      assessment_after=(2, 4, 6))
plan = TreatmentPlan("P", reg, date(2026, 11, 2))
plan.adjustments  # noqa

fig, ax = plt.subplots(figsize=(11, 3.4), dpi=160)
events = plan.build_timeline()
by_cycle = {}
for e in events:
    by_cycle.setdefault(e.cycle, []).append(e)

for c, evs in by_cycle.items():
    adm = next(e for e in evs if e.kind == "admission")
    dis = next(e for e in evs if e.kind == "discharge")
    ax.broken_barh(
        [(matplotlib.dates.date2num(adm.date),
          (dis.date - adm.date).days + 1)],
        (c - 0.28, 0.56), facecolors=BLUE, edgecolor="none")
    ax.text(matplotlib.dates.date2num(adm.date) + 0.4, c,
            f"C{c}", va="center",
            fontsize=9, color="white", weight="bold")
    for e in evs:
        if e.kind == "nadir_check":
            ax.plot(matplotlib.dates.date2num(e.date), c, "o",
                    color=RED, ms=7, zorder=5)
        if e.kind == "assessment":
            ax.plot(matplotlib.dates.date2num(e.date), c, "D",
                    color=ORANGE, ms=8, zorder=5)

# legend
ax.plot([], [], "o", color=RED, label="间隔期血象复查（低谷期）")
ax.plot([], [], "D", color=ORANGE, label="中期疗效评估")
ax.barh([], [], color=BLUE, label="床位占用（住院日）")
ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.42), ncol=3, fontsize=9, frameon=False)
ax.set_yticks(range(1, 7))
ax.set_ylabel("治疗周期", fontsize=10)
ax.set_ylim(0.4, 6.9)
ax.set_title("一张床位被「锁死」4 个月：R-CHOP 21 天 × 6 周期的时间轴"
             "（引擎真实输出）", fontsize=12, pad=10)
ax.grid(axis="x", alpha=.3)
ax.spines[["top", "right", "left"]].set_visible(False)
import matplotlib.dates as mdates
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "图1-周期锁死时间轴.png"))
plt.close(fig)

# ------------------------------------------------------------- figure 2
TODAY = date(2026, 10, 26)
plans = synthetic_plans(TODAY, n=8)

fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), dpi=160,
                         sharey=True)
beds = [Bed("07"), Bed("12"), Bed("15"), Bed("21")]
titles = ["现状：入院扎堆 + 日期漂移 → 床位碎片空洞", "反向排床：按引擎日期均匀铺满 → 无空洞"]
for ax, mode in zip(axes, ("chaos", "reverse")):
    s = BedScheduler(list(beds))
    import random
    rng = random.Random(7 if mode == "chaos" else 42)
    for plan in plans:
        nxt = plan.next_admission(TODAY - timedelta(days=3))
        if not nxt:
            continue
        if mode == "chaos":
            # arrival dates jittered, booked the same day -> conflicts
            d = nxt.date + timedelta(days=rng.randint(-1, 1))  # 现状:日期漂移、扎堆
            bk = s.book(BookingRequest(plan.patient_id, d, 4))
        else:
            bk = s.book(BookingRequest(plan.patient_id, nxt.date, 4))
    grid = s.gantt(TODAY, 14)
    for r, row in enumerate(grid):
        for i, cell in enumerate(row[1:]):
            color = {"X": BLUE, "o": ORANGE, ".": "#eef1f5"}[cell]
            ax.broken_barh([(i, 1)], (len(grid) - 1 - r - 0.35, 0.7),
                           facecolors=color, edgecolor="white")
        ax.text(-0.15, len(grid) - 1 - r, row[0], ha="right",
                va="center", fontsize=10)
    ax.set_xlim(0, 14)
    ax.set_xticks([i + .5 for i in range(14)])
    ax.set_xticklabels([(TODAY + timedelta(days=i)).strftime("%m-%d")
                        for i in range(14)], fontsize=8)
    ax.set_title(titles[0 if mode == "chaos" else 1] , fontsize=10)
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
axes[0].text(7, -1.25, "■ 蓝色=确认入住   ■ 橙色=已预约锁床   □ 空床",
             ha="center", fontsize=9, color="#666")
fig.suptitle("同一批患者、同一周床位：反向排床把「当天抢床」变成「提前日历」"
             "（引擎真实输出）", fontsize=12, y=1.02)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "图2-反向排床对比.png"),
            bbox_inches="tight")
plt.close(fig)
print("figures saved to", os.path.abspath(OUT))
