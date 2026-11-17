"""`f2d review`: the shared reviewer (`doricokit.review`, moved there 2026-10-31) plus the
converter's own check, "not-converted": Finale material the converter could not convert, from
the `<name>.f2d-report.json` that `f2d convert --report` writes next to the project.

    python3 -m f2d review Score.dorico [--json out.json] [--all]
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from doricokit import findings
from doricokit.findings import Finding
from doricokit.review import Reviewer, format_text, review, section_clusters, to_json  # noqa: F401


def _converter_report(ctx: Reviewer) -> None:
    side = Path(ctx.p.path).with_suffix(".f2d-report.json")
    if not side.exists():
        return
    try:
        rep = json.loads(side.read_text())
    except (OSError, json.JSONDecodeError):
        return
    counts = defaultdict(int)
    for w in rep.get("warnings", []):
        counts[re.sub(r"\d+(/\d+)?", "N", w)] += 1
    for pattern, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        ctx.findings.append(Finding("not-converted", "info", "", "", "0", "", f"{pattern} (×{n})" if n > 1 else pattern))


findings.register_check("not-converted", "Finale material the converter could not convert (from its report)",
                        _converter_report, scope="project", owner="finale2dorico")
