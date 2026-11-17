"""Build `timeline-ref.dorico`: the reference project that pins down Dorico's playback timing
for the timeline module (engine/docs/TIMELINE.md, "Reference files").

    uv run python engine/tests/dorico-check/make_timeline_ref.py

One flute, 4/4, crotchets; every bar has its own pitch (bar 1 = C4, bar 2 = D4, ...) so the
MIDI export shows the performed order. One flow per question:

  1 Tempo kinds      ♩=120, then ♩.=60 (bar 5), then minim = crotchet (bar 9)
  2 Rit and accel    ♩=120, rit. bars 3-4 (75%), ♩=120 bar 7, accel. bars 7-8 (125%)
  3 Fermatas         ♩=60; a fermata on beat 3 of bars 2-8 (normal, very short, short, long,
                     very long, short Henze, long Henze), caesura after bar 9 beat 2,
                     breath mark after bar 10 beat 2
  4 Repeats D.S.     start repeat bar 2, 1st ending bar 4, 2nd ending bar 5, segno bar 6,
                     To Coda bar 8, D.S. al Coda bar 9, Coda bar 10
  5 D.C. al Fine     Fine at the end of bar 3, D.C. al Fine in bar 6
  6 No tempo         no tempo mark at all
  7 For you to add   ♩=100; ♩=60 at bar 7; the user adds relative tempos in Dorico (README)

Uses finale2dorico's IR and Dorico writer (read-only use of f2d).
"""

from __future__ import annotations

import sys
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "finale2dorico"))

from f2d import ir  # noqa: E402
from f2d.dorico.install import DoricoInstall  # noqa: E402
from f2d.dorico.writer import DoricoWriter, Options  # noqa: E402

SCALE = [(60, "C"), (62, "D"), (64, "E"), (65, "F"), (67, "G"), (69, "A"), (71, "B"),
         (72, "C"), (74, "D"), (76, "E"), (77, "F"), (79, "G"), (81, "A"), (83, "B"), (84, "C")]


def flow(fid: str, title: str, bars: int) -> tuple[ir.Flow, ir.Staff]:
    chords = []
    for b in range(bars):
        midi, step = SCALE[b % len(SCALE)]
        for beat in range(4):
            chords.append(ir.Chord(pos=F(4 * b + beat), dur=F(1), notated=F(1), pitches=[ir.Pitch(midi, step)]))
    st = ir.Staff(instrument="fl", index=0, clefs=[ir.Clef(F(0), "clef.treble")],
                  voices=[ir.Voice(index=0, chords=chords)])
    f = ir.Flow(id=fid, title=title, length=F(4 * bars),
                time_signatures=[ir.TimeSignature(F(0), 4, 4)],
                staves=[st], bar_starts=[F(4 * b) for b in range(bars)])
    return f, st


def build() -> ir.Score:
    flows = []

    f, _ = flow("1", "1 Tempo kinds", 12)
    f.tempos = [ir.Tempo(F(0), 120.0), ir.Tempo(F(16), 60.0, unit=F(3, 2)),
                ir.Tempo(F(32), None, equation=(F(2), F(1)))]
    flows.append(f)

    f, _ = flow("2", "2 Rit and accel", 10)
    f.tempos = [ir.Tempo(F(0), 120.0), ir.Tempo(F(24), 120.0)]
    f.gradual_tempos = [ir.GradualTempo(F(8), F(16), "rit"), ir.GradualTempo(F(24), F(32), "accel")]
    flows.append(f)

    f, _ = flow("3", "3 Fermatas", 11)
    f.tempos = [ir.Tempo(F(0), 60.0)]
    styles = ["kNormal", "kVeryShort", "kShort", "kLong", "kVeryLong", "kShortHenze", "kLongHenze"]
    f.breaths = [ir.Breath(F(4 * (b + 1) + 2), "fermata", s) for b, s in enumerate(styles)]
    f.breaths += [ir.Breath(F(4 * 8 + 2), "caesura", "kNormal"), ir.Breath(F(4 * 9 + 2), "breath", "kComma")]
    flows.append(f)

    f, _ = flow("4", "4 Repeats D.S.", 10)
    f.tempos = [ir.Tempo(F(0), 120.0)]
    f.barlines = [ir.Barline(F(4), "start_repeat"), ir.Barline(F(16), "end_repeat")]
    f.endings = [ir.Ending(F(12), F(16), [1], "1."), ir.Ending(F(16), F(20), [2], "2.")]
    f.repeat_markers = [ir.RepeatMarker(F(20), section="segno"), ir.RepeatMarker(F(31), jump="to_coda"),
                        ir.RepeatMarker(F(35), jump="ds", until="coda"), ir.RepeatMarker(F(36), section="coda")]
    flows.append(f)

    f, _ = flow("5", "5 D.C. al Fine", 6)
    f.tempos = [ir.Tempo(F(0), 120.0)]
    f.repeat_markers = [ir.RepeatMarker(F(12), section="fine"), ir.RepeatMarker(F(23), jump="dc", until="fine")]
    flows.append(f)

    f, _ = flow("6", "6 No tempo", 4)
    flows.append(f)

    f, _ = flow("7", "7 For you to add", 12)
    f.tempos = [ir.Tempo(F(0), 100.0), ir.Tempo(F(24), 60.0)]
    flows.append(f)

    fl = ir.Instrument(id="fl", name="Flute", short_name="Fl.", dorico_id="instrument.wind.flute")
    return ir.Score(info=ir.Info(title="Timeline reference"),
                    players=[ir.Player(id="p1", name="Flute", instruments=[fl])], flows=flows)


def main() -> None:
    out = Path(__file__).with_name("timeline-ref.dorico")
    w = DoricoWriter(build(), DoricoInstall(), Options(parts=False))
    w.write(out)
    print(f"wrote {out}")
    for line in w.report:
        print("  " + line)


if __name__ == "__main__":
    main()
