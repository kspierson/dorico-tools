"""`f2d clean`: the shared cleaner (`doricokit.clean`, moved there 2026-10-31; docs/CLEANER.md).

    python3 -m f2d clean In.dorico [-o Out.dorico] [--rules dedupe,link] [--dry-run] [--json changes.json]
"""
from doricokit.clean import Cleaner, after_check, clean, default_rules, format_text, to_json  # noqa: F401
