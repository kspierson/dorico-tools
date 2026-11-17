"""Write check/gen-round12.dorico: the Round 12 items as the converter writes them, on a violin,
in the same bars as the user's ref-harmonics-lines.dorico (open it in Dorico to compare).

    uv run python experiments/round12/make_check.py
"""
from __future__ import annotations

import sys
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from f2d import ir  # noqa: E402
from f2d.dorico.install import DoricoInstall  # noqa: E402
from f2d.dorico.writer import DoricoWriter  # noqa: E402

SCALE = [(67, "G", 0), (69, "A", 0), (71, "B", 0), (72, "C", 0), (74, "D", 0), (76, "E", 0), (78, "F", 1), (79, "G", 0)]


def main() -> None:
    chords = []
    for i in range(32):  # 8 bars of crotchets, the user's G major scale
        midi, step, alter = SCALE[i % 8]
        chords.append(ir.Chord(pos=F(i), dur=F(1), notated=F(1), pitches=[ir.Pitch(midi, step, alter)]))
    chords[0].harmonic = "natural"                                     # bar 1 beat 1
    chords[2].harmonic, chords[2].harmonic_partial = "artificial", 3   # bar 1 beat 3: touched 5th
    chords[4].harmonic, chords[4].harmonic_partial = "artificial", 4   # bar 2 beat 1: touched 4th
    chords[6].harmonic, chords[6].harmonic_partial = "artificial", 5   # bar 2 beat 3: touched major 3rd
    chords[12].tremolo = 3                                             # bar 4 beat 1
    chords[8].tremolo_pair, chords[9].tremolo_pair_end = 3, True        # bar 3: two-note tremolos
    chords[10].tremolo_pair, chords[11].tremolo_pair_end = 2, True
    st = ir.Staff(instrument="I1", index=0, voices=[ir.Voice(index=0, chords=chords)])
    st.lines = [
        ir.Line(pos=F(16), end=F(19)),                                             # bar 5: plain solid
        ir.Line(pos=F(20), end=F(24), body="dashed", hook_end=True, text="Cue:"),  # bar 6
        ir.Line(pos=F(24), end=F(28), body="dashed", centre_text="possibile"),     # bar 7: centre word
        ir.Line(pos=F(8), end=F(12), body="wavy", text="continue pattern"),        # bar 3: wavy + words
        ir.Line(pos=F(12), end=F(16), hook_start=True),                            # bar 4: hook at start only
    ]
    st.techniques = [
        ir.Technique(pos=F(5), text="Bright", boxed=True),                         # bar 2 beat 2
        ir.Technique(pos=F(28), text="ord.", kind="ord", group=0),                 # bar 8
        ir.Technique(pos=F(29) + F(1, 2), text="move bow towards..."),
        ir.Technique(pos=F(31), text="sul pont.", kind="sul-pont", group=0),
    ]
    flow = ir.Flow(id="F1", title="Round 12 check", length=F(32),
                   time_signatures=[ir.TimeSignature(pos=F(0), num=4, den=4)],
                   key_signatures=[ir.KeySignature(pos=F(0), fifths=1)],
                   tempos=[ir.Tempo(pos=F(16), equation=(F(2), F(1)), show_metronome=False)],
                   staves=[st], bar_starts=[F(4 * i) for i in range(8)])
    inst = ir.Instrument(id="I1", name="Violin")
    score = ir.Score(players=[ir.Player(id="P1", name="Violin", instruments=[inst])], flows=[flow])
    score.info.title = "Round 12 check"
    out = Path(__file__).parent / "check" / "gen-round12.dorico"
    out.parent.mkdir(exist_ok=True)
    DoricoWriter(score, DoricoInstall()).write(out)
    print(out)


if __name__ == "__main__":
    main()
