"""Explode Finale's shared staves into Dorico players.

Finale is staff-based: a condensed part such as "Horn 1" often carries two players in two
layers (Horns 1 and 3), with "a2" / "1." / "2." marking who plays single-line passages. Dorico
is player-based: each horn is a player, and condensing puts them back on shared staves when
wanted. This IR -> IR transform splits such staves into one player per part.

Rules (from the user's Dorico edit of Willow, Round 5):
- Candidates: single-staff wind/brass instruments whose staff has music in 2+ layers, or whose
  name lists 2+ players ("Horns 1 3", Avatar: pairs written as chords in one layer; user decision
  2026-10-29: always split into players). A staff carrying two instruments ("Bass Tbn." over
  "Tuba", read as "Bass Tbn. / Tuba") becomes one player per instrument.
- Numbering: a name listing the numbers ("Horns 1-2", "1/3", "1 & 3") is used as is. Otherwise a
  staff "<name> n" whose type has N such staves gets players n, n+N, n+2N ... ("Horn 1" + "Horn 2"
  -> 1&3 and 2&4, the pairing the user's file implies); a lone staff gets 1, 2, 3 ...
- Bar by bar: where several layers have music, layer k goes to the k-th player. Chords in a
  single layer are the players notated together: split top-down (upper note -> upper player).
  Where only one line exists, the latest marking decides: "a2" (all play it), "1." / "2." (only that player).
  Before any marking: `initial` ("a2" by default).
- Staff-level items (clefs, dynamics, hairpins, playing techniques) go to every new player;
  voice items (slurs, tuplets, trills, glissandi) stay with their layer. The a2/1./2. markings
  are consumed (Dorico shows its own labels when condensing).
- New players are placed right after the source player (Hn 1, Hn 3, Hn 2, Hn 4).
"""
from __future__ import annotations

import copy
import re
from collections import defaultdict
from fractions import Fraction

from . import ir

MONOPHONIC = re.compile(r"flute|piccolo|oboe|english horn|cor anglais|clarinet|bassoon|"
                        r"saxophone|sax|horn|trumpet|cornet|flugel|trombone|tuba|euphonium|"
                        r"baritone|recorder", re.I)
MONOPHONIC_SOUND = re.compile(r"^(wind|brass)", re.I)  # "brass.french-horn" or "brassFrenchHorn"


def _base_and_numbers(name: str) -> tuple[str, list[int]]:
    m = re.match(r"^(.*?)[\s.]*((?:\d+\s*(?:[-&/,.+]|and)?\s*)+)$", name.strip())
    if not m:
        return name.strip(), []
    base, nums = m.group(1).strip(), m.group(2)
    if re.search(r"\d+\s*-\s*\d+", nums):
        a, b = map(int, re.findall(r"\d+", nums)[:2])
        return base, list(range(a, b + 1))
    return base, [int(x) for x in re.findall(r"\d+", nums)]


def _layers_with_music(st: ir.Staff) -> list[int]:
    return sorted({v.layer or 1 for v in st.voices if any(c.pitches for c in v.chords)})


def _bars(flow: ir.Flow) -> list[tuple[Fraction, Fraction]]:
    starts = flow.bar_starts + [flow.length]
    return list(zip(starts, starts[1:]))


def _take_divided(v: ir.Voice, a: Fraction, b: Fraction, out_voices: dict, targets: list[int]) -> None:
    """Split chords in bar [a, b) of voice v across the players: highest note -> player 0, next
    -> player 1 ...; the last player also gets any extra lower notes. Single notes go to
    `targets` (per the a2/1./2. marking). Slurs/tuplets/trills/glissandi go to every player."""
    n = len(out_voices)
    for c in v.chords:
        if not (a <= c.pos < b):
            continue
        if len(c.pitches) >= 2:
            ps = sorted(c.pitches, key=lambda p: -p.midi)
            for k in range(n):
                part = ps[k:k + 1] if k < n - 1 else ps[k:]
                if part:
                    cc = copy.deepcopy(c)
                    cc.pitches = copy.deepcopy(part)
                    out_voices[k].chords.append(cc)
        else:
            for k in (targets if c.pitches else range(n)):
                out_voices[k].chords.append(copy.deepcopy(c))
    for k in range(n):
        dst = out_voices[k]
        dst.tuplets += [copy.deepcopy(t) for t in v.tuplets if a <= t.pos < b]
        dst.slurs += [copy.deepcopy(s) for s in v.slurs if a <= s.pos < b]
        dst.trills += [copy.deepcopy(t) for t in v.trills if a <= t.pos < b]
        dst.glissandi += [copy.deepcopy(g) for g in v.glissandi if a <= g.pos < b]


def explode(score: ir.Score, initial: str = "a2") -> list[str]:
    """Split shared staves in place. Returns report lines."""
    report: list[str] = []
    if not score.flows:
        return report
    flow = score.flows[0]
    staff_of = {(st.instrument, st.index): st for st in flow.staves}
    cands = []
    paired = False
    for p in list(score.players):
        for inst in p.instruments:
            st = staff_of.get((inst.id, 0))
            if inst.num_staves != 1 or st is None:
                continue
            mono = MONOPHONIC.search(inst.name or "") or MONOPHONIC_SOUND.search(inst.sound_id or "")
            layers = _layers_with_music(st)
            pair = _instrument_pair(inst.name)
            if pair and layers:  # "Bass Tbn. / Tuba": one player each
                _split(score, flow, p, inst, st, layers, pair, initial, report)
                paired = True
                continue
            # 2+ layers, or a name listing 2+ players ("Horns 1 3") written as chords in one layer
            if mono and (len(layers) >= 2 or (layers and len(_base_and_numbers(inst.name)[1]) >= 2)):
                cands.append((p, inst, st))
    by_type = defaultdict(list)
    for p, inst, st in cands:
        by_type[_base_and_numbers(inst.name)[0]].append((p, inst, st))
    for base, group in by_type.items():
        n_staves = len(group)
        # "Horn 1" + "Horn 2" (every staff one number) -> pairs 1&3, 2&4; otherwise count on
        interleave = all(len(_base_and_numbers(i.name)[1]) == 1 for _, i, _ in group) and n_staves > 1
        next_free = 1
        for p, inst, st in group:
            layers = _layers_with_music(st)
            _, nums = _base_and_numbers(inst.name)
            if len(layers) == 1 and 2 <= len(nums) <= 4:
                numbers = nums  # chords in one layer: one player per listed number
            elif len(nums) >= len(layers):
                numbers = nums[:len(layers)]
            elif len(nums) == 1 and interleave:
                numbers = [nums[0] + k * n_staves for k in range(len(layers))]
            elif len(nums) == 1:
                numbers = list(range(nums[0], nums[0] + len(layers)))
            else:
                numbers = list(range(next_free, next_free + len(layers)))
            next_free = max(numbers) + 1
            single = _singular(base)
            _split(score, flow, p, inst, st, layers, [f"{single} {n}" for n in numbers], initial, report)
    if cands or paired:  # shared staves became players: let Dorico condense them again in the full score
        score.layout = score.layout or ir.Layout()
        score.layout.condense = True
    return report


def _instrument_pair(name: str) -> list[str] | None:
    """'Bass Tbn. / Tuba' (the reader's form of a two-line Finale name) -> ['Bass Tbn.', 'Tuba']."""
    parts = [x.strip() for x in (name or "").split(" / ")]
    return parts if len(parts) == 2 and all(parts) else None


def _singular(base: str) -> str:
    """'Horns' -> 'Horn' (player names); leaves 'Bass', 'Cymbals'... alone unless monophonic."""
    if base.endswith("s") and not base.endswith("ss") and MONOPHONIC.fullmatch(base[:-1].split()[-1] or ""):
        return base[:-1]
    return base


def _split(score, flow, player, inst, st, layers, labels, initial, report) -> None:
    """Split staff st into len(labels) players. Bars where several layers have music: layer k
    -> player k. Bars with one layer: chords split top-down, single notes follow a2/1./2."""
    bars = _bars(flow)
    n = len(labels)
    marks = sorted((t.pos, t.kind) for t in st.techniques
                   if t.kind and (t.kind.startswith("solo") or re.fullmatch(r"a\d", t.kind)))

    def state_at(pos: Fraction) -> str:
        cur = initial
        for p, k in marks:
            if p <= pos:
                cur = k
        return cur

    layer_voices = {L: [v for v in st.voices if (v.layer or 1) == L] for L in layers}
    kept = [t for t in st.techniques if not (t.kind and (t.kind.startswith("solo") or re.fullmatch(r"a\d", t.kind)))]
    out_staves = {k: ir.Staff(instrument="", index=0, clefs=copy.deepcopy(st.clefs),
                              dynamics=copy.deepcopy(st.dynamics), hairpins=copy.deepcopy(st.hairpins),
                              techniques=copy.deepcopy(kept), ottavas=copy.deepcopy(st.ottavas),
                              pedals=copy.deepcopy(st.pedals), harp_pedals=copy.deepcopy(st.harp_pedals),
                              time_signatures=copy.deepcopy(st.time_signatures),
                              pauses=copy.deepcopy(st.pauses), lines=copy.deepcopy(st.lines))
                  for k in range(n)}
    out_voices = {k: ir.Voice(index=0, layer=1) for k in range(n)}

    def take(v: ir.Voice, a: Fraction, b: Fraction, k: int) -> None:
        """Copy v's material in bar [a, b) into player k's voice."""
        dst = out_voices[k]
        dst.chords += [copy.deepcopy(c) for c in v.chords if a <= c.pos < b]
        dst.tuplets += [copy.deepcopy(t) for t in v.tuplets if a <= t.pos < b]
        dst.slurs += [copy.deepcopy(s) for s in v.slurs if a <= s.pos < b]
        dst.trills += [copy.deepcopy(t) for t in v.trills if a <= t.pos < b]
        dst.glissandi += [copy.deepcopy(g) for g in v.glissandi if a <= g.pos < b]

    assumed = []
    for a, b in bars:
        active = [L for L in layers
                  if any(c.pitches and a <= c.pos < b for v in layer_voices[L] for c in v.chords)]
        if len(active) >= 2:
            for k, L in enumerate(layers[:n]):
                for v in layer_voices[L]:
                    take(v, a, b, k)
            continue
        if not active:
            continue
        src = active[0]
        first = min(c.pos for v in layer_voices[src] for c in v.chords if c.pitches and a <= c.pos < b)
        state = state_at(first)
        if not any(p <= first for p, _ in marks):
            assumed.append(a)
        if state.startswith("solo"):
            k = int(state[4:]) - 1
            targets = [min(max(k, 0), n - 1)]
        else:  # a2 / a3: everyone plays the single line
            targets = list(range(n))
        divided = any(len(c.pitches) >= 2 for v in layer_voices[src] for c in v.chords if a <= c.pos < b)
        for v in layer_voices[src]:
            if divided:
                # chords in one layer = the players notated together (Willow bar 7): split each
                # chord top-down, upper note -> upper player; single notes follow the marking
                _take_divided(v, a, b, out_voices, targets)
            else:
                for k in targets:
                    take(v, a, b, k)

    # dynamics/hairpins only for players who play there (a dynamic on a player's rest helps
    # nobody; the reviewer flagged Horn 3 getting bar 1's f): keep an item for a player who has
    # a note sounding at it or starting within a beat; if nobody does, everyone keeps it
    def plays(k, p):
        return any(c.pitches and (c.pos <= p < c.pos + max(c.dur, Fraction(1, 64)) or p <= c.pos < p + 1)
                   for c in out_voices[k].chords)
    for attr in ("dynamics", "hairpins"):
        for item in getattr(st, attr):
            who = [k for k in range(n) if plays(k, item.pos)]
            if not who or len(who) == n:
                continue
            for k in range(n):
                if k not in who:
                    lst = getattr(out_staves[k], attr)
                    for x in list(lst):
                        if x.pos == item.pos and x == item:
                            lst.remove(x)
                            break

    # replace the source staff's music with player 1's; add the others as new players
    new_players = []
    idx = score.players.index(player)
    player.condense_group = player.id
    for k, label in enumerate(labels):
        voice = out_voices[k]
        voice.chords.sort(key=lambda c: (c.pos, not c.grace))
        stf = out_staves[k]
        stf.voices = [voice]
        if k == 0:
            inst.name = label
            player.name = inst.name
            st.voices, st.techniques = stf.voices, stf.techniques
            st.dynamics, st.hairpins = stf.dynamics, stf.hairpins
            continue
        new_inst = copy.deepcopy(inst)
        new_inst.id = f"{inst.id}x{k}"
        new_inst.name = label
        new_inst.dorico_id = None
        num = re.search(r"(\d+)$", label)
        new_inst.short_name = re.sub(r"\s*\d+$", "", inst.short_name or "").strip() + f" {num.group(1)}" \
            if inst.short_name and num else ""
        stf.instrument = new_inst.id
        new_players.append(ir.Player(id=f"{player.id}x{k}", name=new_inst.name, instruments=[new_inst],
                                     condense_group=player.id))
        flow.staves.insert(flow.staves.index(st) + k, stf)
    score.players[idx + 1:idx + 1] = new_players
    msg = f"staff '{labels[0]}' split into players {', '.join(labels)}"
    if assumed:
        msg += f" (single-line bars before the first a2/1./2. marking treated as '{initial}')"
    report.append(msg)
