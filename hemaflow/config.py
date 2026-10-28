"""Rules as data (规则配置加载).

Regimen templates and alert thresholds live in a JSON file owned by
the clinical team (see config/rules.example.json). The engine reads
configuration - it never hardcodes medical policy.

Keeping JSON (not YAML) keeps the core package zero-dependency.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .alerts import AlertThresholds
from .engine import RegimenTemplate

_REQUIRED_REGIMEN = {"name", "cycles", "cycle_length_days",
                     "inpatient_days"}


def load_rules(path: str | Path) -> dict:
    """Load a rules file (加载规则文件).

    Returns dict with:
      regimens: dict[name, RegimenTemplate]
      alert_thresholds: dict[group, AlertThresholds]
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    regimens: dict = {}
    for r in raw.get("regimens", []):
        missing = _REQUIRED_REGIMEN - set(r)
        if missing:
            raise ValueError(f"regimen missing fields: {missing}")
        regimens[r["name"]] = RegimenTemplate(
            name=r["name"],
            cycles=int(r["cycles"]),
            cycle_length_days=int(r["cycle_length_days"]),
            inpatient_days=int(r["inpatient_days"]),
            nadir_days=tuple(r.get("nadir_days", (7, 12))),
            assessment_after=tuple(r.get("assessment_after", ())),
            drugs=tuple(r.get("drugs", ())),
        )
    thresholds: dict = {}
    for group, t in raw.get("alert_thresholds", {}).items():
        thresholds[group] = AlertThresholds(
            anc_yellow=float(t["anc_yellow"]),
            anc_red=float(t["anc_red"]),
            plt_red=float(t["plt_red"]),
            fever_celsius=float(t.get("fever_celsius", 38.0)),
        )
    return {"regimens": regimens, "alert_thresholds": thresholds}


def load_regimens(path: str | Path) -> List[RegimenTemplate]:
    return list(load_rules(path)["regimens"].values())


def load_thresholds(path: str | Path, group: str = "default"
                    ) -> AlertThresholds:
    th = load_rules(path)["alert_thresholds"]
    if group not in th:
        raise KeyError(f"threshold group not found: {group}")
    return th[group]
