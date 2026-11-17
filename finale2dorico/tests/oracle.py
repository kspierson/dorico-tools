"""Compare the Finale reader's IR against the MusicXML a .musx file was made from.

The HPCaptures test files (dorico-hp project) were created by importing known MusicXML
into Finale, so the MusicXML is an independent record of the notes. This checks
pitch (concert), position and sounding duration of every note, per staff.

    python3 tests/oracle.py [--reader bootstrap|musxdom] <musx dir> <musicxml dir> [name ...]

--reader musxdom checks the full reader (C++ extractor, f2d/finale/facts.py) instead of the
bootstrap Python reader.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f2d.finale.enigma import read_musx  # noqa: E402

READ = read_musx

STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _q(x: Fraction) -> Fraction:
    """Compare on a 1/192-crotchet grid: Finale's MusicXML export rounds tuplets to its
    divisions (a quintuplet semiquaver comes out as 205/1024)."""
    return Fraction(round(x * 192), 192)


def musicxml_notes(path: Path) -> dict[int, Counter]:
    """{global staff index: Counter((pos, dur, midi, tie_start))}, concert pitch."""
    root = ET.parse(path).getroot()
    out: dict[int, Counter] = {}
    staff_base = 0
    for part in root.findall("part"):
        divisions = 1
        pos = Fraction(0)
        chroma = 0
        n_staves = 1
        last_start = Fraction(0)
        bar_start, bar_len = Fraction(0), Fraction(4)
        for meas in part.findall("measure"):
            # each bar restarts at its proper start: Finale exports under/over-full bars as is,
            # and running sums would shift everything after them
            pos = bar_start
            extent = bar_start
            for el in meas:
                if el.tag == "attributes":
                    tm = el.find("time")
                    if tm is not None and tm.findtext("beats") and tm.findtext("beat-type"):
                        try:
                            bar_len = Fraction(sum(int(x) for x in tm.findtext("beats").split("+")) * 4,
                                               int(tm.findtext("beat-type")))
                        except ValueError:
                            pass
                    if el.findtext("divisions"):
                        divisions = int(el.findtext("divisions"))
                    if el.findtext("staves"):
                        n_staves = int(el.findtext("staves"))
                    t = el.find("transpose")
                    if t is not None:
                        chroma = int(t.findtext("chromatic") or 0) + 12 * int(t.findtext("octave-change") or 0)
                elif el.tag == "backup":
                    pos -= Fraction(int(el.findtext("duration")), divisions)
                elif el.tag == "forward":
                    pos += Fraction(int(el.findtext("duration")), divisions)
                elif el.tag == "note":
                    grace = el.find("grace") is not None
                    dur = Fraction(int(el.findtext("duration") or 0), divisions)
                    chord = el.find("chord") is not None
                    start = last_start if chord else pos
                    if not chord:
                        last_start = pos
                    p = el.find("pitch")
                    staff = int(el.findtext("staff") or 1) - 1
                    if p is not None and not grace:
                        midi = (int(p.findtext("octave")) + 1) * 12 + STEP[p.findtext("step")] + \
                            int(float(p.findtext("alter") or 0))
                        tie = any(t.get("type") == "start" for t in el.findall("tie"))
                        out.setdefault(staff_base + staff, Counter())[(_q(start), _q(dur), midi + chroma, tie)] += 1
                    if not chord and not grace:
                        pos = start + dur
                extent = max(extent, pos)
            bar_start += (extent - bar_start) if meas.get("implicit") == "yes" else bar_len
        staff_base += n_staves
    return out


def ir_notes(score) -> dict[int, Counter]:
    out: dict[int, Counter] = {}
    staves = score.flows[0].staves
    index = {(st.instrument, st.index): k for k, st in enumerate(staves)}
    for k, st in enumerate(staves):
        out.setdefault(k, Counter())
        for v in st.voices:
            for ch in v.chords:
                if ch.grace or ch.is_rest:
                    continue
                for p in ch.pitches:
                    # cross-staff notes count on the staff they are drawn on (as in MusicXML)
                    kk = index.get((st.instrument, p.staff), k) if p.staff is not None else k
                    out.setdefault(kk, Counter())[(_q(ch.pos), _q(ch.dur), p.midi, p.tie)] += 1
    return out


def compare(musx: Path, mxl: Path) -> tuple[bool, str]:
    score = READ(musx)
    a, b = musicxml_notes(mxl), ir_notes(score)
    lines = []
    ok = True
    for k in sorted(set(a) | set(b)):
        missing = a.get(k, Counter()) - b.get(k, Counter())
        extra = b.get(k, Counter()) - a.get(k, Counter())
        if missing or extra:
            ok = False
            lines.append(f"  staff {k}: {sum(missing.values())} missing, {sum(extra.values())} extra")
            for x in sorted(missing)[:4]:
                lines.append(f"    - {tuple(str(v) for v in x)}")
            for x in sorted(extra)[:4]:
                lines.append(f"    + {tuple(str(v) for v in x)}")
    n = sum(sum(c.values()) for c in a.values())
    return ok, f"{musx.stem}: {'OK' if ok else 'DIFF'} ({n} notes)" + ("\n" + "\n".join(lines) if lines else "")


def main(argv: list[str]) -> int:
    global READ
    if argv[:1] == ["--reader"]:
        if argv[1] == "musxdom":
            from f2d.finale.facts import read_finale
            READ = read_finale
        argv = argv[2:]
    musx_dir, mxl_dir = Path(argv[0]), Path(argv[1])
    names = argv[2:] or sorted(p.stem for p in musx_dir.glob("*.musx"))
    bad = 0
    for name in names:
        mxl = mxl_dir / f"{name}.musicxml"
        if not mxl.exists():
            continue
        try:
            ok, msg = compare(musx_dir / f"{name}.musx", mxl)
        except Exception as e:  # report and keep going
            ok, msg = False, f"{name}: ERROR {type(e).__name__}: {e}"
        bad += not ok
        print(msg)
    print(f"{bad} file(s) with differences")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
