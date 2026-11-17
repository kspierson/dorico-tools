"""Layout options: page size, staff size, condensing and empty-stave hiding.

Every layout starts from the user's new-project `layoutOptions` (f2d/data/
new_project_layout_options.xml, or a seed project's). Then the source's page setup is applied:

- page size and staff size (Dorico `defaultSpaceSize`, the space between two staff lines, in
  points) from Finale's page format;
- if a full-score system would not fit the page at that size (Dorico then squashes the staves
  together), the staff size is reduced until it fits at comfortable gaps; below a readable
  minimum the page grows to 11x17 first;
- `hideEmptyStavesPolicy` when Finale's systems leave out empty staves;
- condensing in the full score when shared Finale staves were split into players.

Units: points (1/72 inch), as in Dorico's file (Letter = 612 x 792, A4 = 594 x 841).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from doricokit import format as dtn

from .. import ir
from .tree import Node, deep_copy

DATA = Path(__file__).resolve().parents[1] / "data" / "new_project_layout_options.xml"

GAP = 5.0            # spaces between staves we aim for when fitting (Dorico: ideal 6, minimum 4)
MIN_SPACE = 2.0      # pt (0.7 mm; a 2.8 mm staff), the smallest staff size we choose
TABLOID = (792.0, 1224.0)
HIDE = {"never": "kNever", "after_first": "kAfterFirstSystem", "all": "kAllSystems"}


@lru_cache(maxsize=1)
def _defaults() -> dict[str, Node]:
    root = dtn.from_xml(DATA.read_bytes()).root
    return {c.tag: c.child("layoutOptions") for c in root.children or []}


def default_options(layout_type: str) -> Node | None:
    d = _defaults().get(layout_type)
    return deep_copy(d) if d is not None else None


def _set(opts: Node, path: str, value) -> None:
    n = opts.find(path)
    if n is not None:
        n.value = _fmt(value) if isinstance(value, float) else str(value)


def _get(opts: Node, path: str, default: float) -> float:
    n = opts.find(path)
    try:
        return float(n.value) if n is not None and n.value else default
    except ValueError:
        return default


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fit_space(opts: Node, page_h: float, n_staves: int) -> float:
    """Largest staff space (pt) at which n_staves fit one page with GAP-space gaps."""
    top = _get(opts, "pageSizeAndMarginOptions/margins/margins/top", 42)
    bottom = _get(opts, "pageSizeAndMarginOptions/margins/margins/bottom", 42)
    pad = _get(opts, "pageSizeAndMarginOptions/defaultMusicFrameTopPadding", 40) + \
        _get(opts, "pageSizeAndMarginOptions/defaultMusicFrameBottomPadding", 30)
    usable = page_h - top - bottom - pad
    spaces = n_staves * 4 + max(n_staves - 1, 0) * GAP
    return usable / spaces if spaces else 99.0


def apply_full_score(opts: Node, lay: ir.Layout | None, n_staves: int, report: list[str]) -> None:
    lay = lay or ir.Layout()
    w, h = lay.page_width, lay.page_height
    space = lay.space or _get(opts, "defaultSpaceSize", 4.96)
    fit = fit_space(opts, h, n_staves)
    if fit < MIN_SPACE and h < TABLOID[1]:
        w, h = (TABLOID[1], TABLOID[0]) if w > h else TABLOID
        report.append(f"layout: {n_staves} staves do not fit the source page; using 11x17")
        fit = fit_space(opts, h, n_staves)
    if space > fit:
        new = max(fit, MIN_SPACE)
        report.append(f"layout: staff size {space * 4 * 25.4 / 72:.1f} mm -> {new * 4 * 25.4 / 72:.1f} mm "
                      f"so {n_staves} staves fit the page")
        space = new
    _set(opts, "pageSizeAndMarginOptions/pageWidth", round(w))
    _set(opts, "pageSizeAndMarginOptions/pageHeight", round(h))
    _set(opts, "defaultSpaceSize", round(space, 2))
    _set(opts, "hideEmptyStavesPolicy", HIDE.get(lay.hide_empty, "kNever"))
    if lay.condense:
        _set(opts, "condensingLayoutOptions/enableCondensing", "true")
    if lay.concert_pitch is not None:  # as Finale displays the score
        _set(opts, "transpositionType", "kScoreInC" if lay.concert_pitch else "kTransposingScore")


def apply_part(opts: Node, lay: ir.Layout | None) -> None:
    if lay is None:
        return
    if lay.part_page_width and lay.part_page_height:
        _set(opts, "pageSizeAndMarginOptions/pageWidth", round(lay.part_page_width))
        _set(opts, "pageSizeAndMarginOptions/pageHeight", round(lay.part_page_height))
    if lay.part_space:
        _set(opts, "defaultSpaceSize", round(lay.part_space, 2))
