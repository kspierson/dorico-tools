"""Apply: write the engine's performance into a copy of a Dorico project.

    python3 -m doricohp.apply IN.dorico OUT.dorico [--style Romantic] [--project-file P.hp.toml]
                              [--only velocity,timing,vibrato] [--dry-run]

Writes playback-only data (nothing that shows in Write mode):
- velocity (kNoteVelocity) on notes of instruments whose expression map carries dynamics on
  a controller, where velocity only shapes the attack. Instruments whose dynamics *are*
  velocity are left alone until test J shows how a stored velocity combines with Dorico's
  own (research/dorico-integration.md);
- played start/end offsets (kEventPlayStartOffset/EndOffset, 480 ticks per crotchet) for
  rhythmic feel and per-library attack latency;
- vibrato controller curves (Play-mode automation), only on controllers the instrument's
  expression map doesn't use for dynamics or technique switches;
- the Dynamics lane (`kDynamic` automation, absolute Dorico levels; tests I/I2) where the
  engine's shaping (phrase swells, espressivo, open-hairpin returns, balance) differs from the
  written dynamics, with accent/marcato boosts added back (`lane.py`). Instruments whose lane
  the user has drawn in are left alone.

Safety:
- never overwrites the source project;
- leaves notes alone that already carry the user's own velocity/offset edits;
- records everything it wrote in OUT.dorico.hp-apply.json; when IN.dorico has such a
  record (re-applying to an earlier output), it first restores the original values and
  removes its own automation, so repeated runs don't stack.
"""
from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path

from dataclasses import replace as dc_replace

from . import engine, lane, model
from .passages import effective_articulations
from .playback import PlaybackSetup
from .profiles import Profiles
from .project import GROUP, PLAY_END, PLAY_START, TICKS_PER_CROTCHET, VELOCITY, Project, get_prop, items, set_prop

WRITES = ("velocity", "timing", "vibrato", "dynamics")


def played_length(n, setup: PlaybackSetup, instrument_id: str) -> Fraction:
    """The played length Dorico itself would give this note (playback options + the
    instrument's expression-map overrides): base %, articulation %, slur (legato) %."""
    def pct(name: str, default: int) -> int:
        try:
            return int(float(setup.option(f"timingOptions.{name}", instrument_id, str(default))))
        except ValueError:
            return default
    p = pct("noteDurationPercent", 95)
    arts = n.articulations
    if "staccatissimo" in arts:
        p = pct("staccatissimoDurationPercent", 25)
    elif "staccato" in arts or "spiccato" in arts:
        p = pct("staccatoDurationPercent", 50)
    elif "staccato-tenuto" in arts:
        p = (pct("staccatoDurationPercent", 50) + pct("tenutoDurationPercent", 98)) // 2
    elif "tenuto" in arts:
        p = pct("tenutoDurationPercent", 98)
    elif "marcato" in arts:
        p = pct("marcatoDurationPercent", 95)
    elif n.slur in ("start", "in"):
        p = pct("legatoDurationPercent", 105)
    return n.dur * Fraction(p, 100)


def capped_length(n, length: Fraction, ms_per_crotchet: float, settings: dict, light: bool = False) -> Fraction:
    """Cap short articulations in time (beyond Dorico/HP, which only use percentages)."""
    a = settings.get("articulation", {})
    arts = n.articulations
    cap = None
    if "staccatissimo" in arts:
        cap = a.get("staccatissimo_max_ms")
    elif "staccato" in arts or "spiccato" in arts:
        cap = a.get("staccato_max_ms")
    if cap is None:
        return length
    if light:
        cap *= a.get("light_factor", 1.0)
    cap = max(cap, a.get("min_ms", 0))
    ms = float(length) * ms_per_crotchet
    if ms > cap:
        length = Fraction(cap / ms_per_crotchet).limit_denominator(1920)
    floor = Fraction(a.get("min_ms", 0) / ms_per_crotchet).limit_denominator(1920)
    return max(length, min(floor, n.dur))


def _write_lane(project: Project, flow, pp, setup: PlaybackSetup, record: dict) -> str:
    """Draw the shaping into the instrument's Dynamics lane; returns a report fragment."""
    iid = pp.part.instrument_id
    block = project.automation_block(flow, iid, create=False)
    if block is not None and any(e.find("data/controllerDefinition") is not None
                                 and e.find("data/controllerDefinition").value == "kDynamic"
                                 for e in items(block)):
        return "dynamics lane NOT written: you have drawn in it"
    def delta(name: str, default: float) -> float:
        try:
            return float(setup.option(f"dynamicsOptions.{name}", iid, str(default)))
        except ValueError:
            return default
    acc, marc = delta("accentDynamicDelta", 0.5), delta("marcatoDynamicDelta", 0.8)
    lo, hi = delta("minProfileLevelForPlayback", -6), delta("maxProfileLevelForPlayback", 6)
    spans = lane.spans(pp)
    n = 0
    for a, b in spans:
        pts = lane.points(pp, a, b, acc, marc, lo=lo, hi=hi)
        if len(pts) < 2:
            continue
        record["groups"].append(project.add_curve(flow, iid, "kDynamic", pts))
        n += 1
    if not n:
        return ""
    total = sum(float(b - a) for a, b in spans)
    return f"dynamics lane: {n} spans ({total:.0f} crotchets)"


def _record_path(p: str | Path) -> Path:
    return Path(str(p) + ".hp-apply.json")


def _undo_previous(project: Project, record: dict) -> int:
    """Restore values recorded by an earlier Apply and remove its automation."""
    by_id = {}
    for flow in project.flows():
        for inst in project.instruments(flow):
            for n in project.notes(flow, inst):
                by_id[n.event_id] = n.node
    restored = 0
    for eid, old in record.get("notes", {}).items():
        node = by_id.get(eid)
        if node is None:
            continue
        for prop, val in old.items():
            set_prop(node, prop, val)
        restored += 1
    groups = set(record.get("groups", []))
    if groups:
        for flow in project.flows():
            for inst in project.instruments(flow):
                project.remove_curves(flow, inst.instrument_id, groups)
    return restored


def apply(src: str, dest: str, style: str | None = None, project_file: str | None = None,
          only: tuple[str, ...] = WRITES, dry_run: bool = False) -> list[str]:
    report: list[str] = []
    project = Project(src)
    prev = _record_path(src)
    if prev.exists():
        n = _undo_previous(project, json.loads(prev.read_text()))
        report.append(f"undid previous Apply on {n} notes ({prev.name})")
    setup = PlaybackSetup(project)
    if project_file is None:
        guess = Path(src).with_suffix(".hp.toml")
        project_file = str(guess) if guess.exists() else None
    profiles = Profiles(style, project_file)
    report.append(f"style {profiles.style['name']}" + (f", project settings {project_file}" if project_file else ""))

    # overlaps with Dorico's own humanising
    opt = setup.options
    if "velocity" in only and float(opt.get("dynamicsOptions.primaryBeatStressDelta", 0) or 0):
        report.append("note: Dorico's beat stress is on (Playback Options ▸ Dynamics) as well as Apply's metric "
                      "accents; consider setting it to 0")
    if "timing" in only and int(opt.get("timingOptions.timingHumanisePercent", 0) or 0):
        report.append(f"note: Dorico's timing humanise is {opt['timingOptions.timingHumanisePercent']}% as well as "
                      "Apply's rhythmic feel; consider 0")
    swing = opt.get("timingOptions.defaultRhythmicFeel", "rhythmicfeel.straight")

    record = {"source": str(src), "style": profiles.style["name"], "notes": {}, "groups": []}
    # notation from the file; note refs re-attached to the in-memory project we save
    scores = _scores_from_project(project, src)
    for sc in scores:
        flow = sc.flow_node
        info = {}
        for part in sc.parts:
            ip = setup.instruments.get(part.instrument_id)
            mp = ip.map if ip else None
            info[part.instrument_id] = (mp.name if mp else "", ip.plugins[0] if ip and ip.plugins else "", part.entity)
        if swing != "rhythmicfeel.straight":
            report.append(f"note: project default rhythmic feel is {swing}; Apply's weak-beat delays are scaled "
                          "by timing.under_swing (default 0 = off) for the whole flow")
            profiles.project = {**profiles.project, "timing": {**profiles.project.get("timing", {}),
                                "ms_per_unit": profiles.defaults["timing"]["ms_per_unit"]
                                * profiles.defaults["timing"]["under_swing"]}}
        perfs = engine.perform(sc, profiles, info)
        for pp in perfs:
            part = pp.part
            ip = setup.instruments.get(part.instrument_id)
            mp = ip.map if ip else None
            nat = mp.natural if mp else None
            dyn_is_velocity = nat is None or nat.volume is None or nat.volume.kind == "vel"
            line = [f"{sc.title or 'flow'} / {part.name}: {pp.settings['library']}, map "
                    f"{mp.name if mp else '?'} (dynamics {nat.volume if nat and nat.volume else 'velocity'})"]
            n_vel = n_tim = n_skip = 0
            # next onset (position, shift in ticks) after each note, same part, any voice
            next_onsets = {}
            ordered = sorted(pp.notes, key=lambda x: x.note.pos)
            onset_list = [(x.note.pos, int(round(x.start_ms / sc.ms_per_crotchet(x.note.pos) * TICKS_PER_CROTCHET)))
                          for x in ordered if not x.note.grace]
            j = 0
            for x in ordered:
                while j < len(onset_list) and onset_list[j][0] <= x.note.pos:
                    j += 1
                if j < len(onset_list):
                    next_onsets[id(x.note)] = onset_list[j]
            for npf in pp.notes:
                ref = npf.note.ref
                if ref is None:
                    continue
                node = ref.node
                user_edit = any(get_prop(node, k) is not None for k in (VELOCITY, PLAY_START, PLAY_END))
                if user_edit:
                    n_skip += 1
                    continue
                old = {}
                if "velocity" in only and not dyn_is_velocity:
                    old[VELOCITY] = get_prop(node, VELOCITY)
                    set_prop(node, VELOCITY, f"int: {npf.velocity}")
                    n_vel += 1
                if "timing" in only:
                    # Once a note has played offsets Dorico no longer applies its own length
                    # percentages (staccato etc.), so the end is always written explicitly:
                    # Dorico's own played length for this note, moved with the onset shift.
                    mpc = sc.ms_per_crotchet(npf.note.pos)
                    n = npf.note
                    t0 = int(round(npf.start_ms / mpc * TICKS_PER_CROTCHET))
                    if n.pos * TICKS_PER_CROTCHET + t0 < 0:
                        t0 = 0
                    state = part.passage.at(n.pos) if part.passage else set()
                    nxt = next_onsets.get(id(n))
                    rest_after = nxt is None or nxt[0] > n.end
                    eff = dc_replace(n, articulations=effective_articulations(n, state, rest_after))
                    length = capped_length(eff, played_length(eff, setup, part.instrument_id), mpc, pp.settings,
                                           light="light" in state)
                    end = n.pos + length + Fraction(t0, TICKS_PER_CROTCHET)
                    if nxt is not None and n.slur not in ("start", "in"):
                        gap = Fraction(pp.settings["timing"].get("min_gap_ms", 25) / mpc).limit_denominator(960)
                        end = min(end, nxt[0] + Fraction(nxt[1], TICKS_PER_CROTCHET) - gap)
                    end = max(end, n.pos + Fraction(t0, TICKS_PER_CROTCHET) + n.dur / 8)
                    t1 = int(round((end - n.end) * TICKS_PER_CROTCHET))
                    old[PLAY_START] = get_prop(node, PLAY_START)
                    old[PLAY_END] = get_prop(node, PLAY_END)
                    set_prop(node, PLAY_START, f"int: {t0}" if t0 else None)
                    set_prop(node, PLAY_END, f"int: {t1}")
                    n_tim += 1
                if old:
                    record["notes"][ref.event_id] = old
            parts_written = []
            if n_vel:
                parts_written.append(f"{n_vel} attack velocities")
            elif "velocity" in only and dyn_is_velocity:
                parts_written.append("velocity left to Dorico (dynamics are velocity)")
            if n_tim:
                parts_written.append(f"{n_tim} timing offsets")
            if n_skip:
                parts_written.append(f"{n_skip} notes skipped (your own Play-mode edits)")
            if "vibrato" in only and pp.ccs:
                owned = (mp.dynamics_controllers() | mp.switched_controllers()) if mp else set()
                for cc, pts in pp.ccs.items():
                    if cc in owned:
                        parts_written.append(f"vibrato CC{cc} NOT written: the expression map uses it")
                        continue
                    pts = [(p, v) for p, v in pts if p >= 0]
                    if not pts:
                        continue
                    g = project.add_curve(flow, part.instrument_id, f"kMIDICC:{cc}", pts)
                    record["groups"].append(g)
                    parts_written.append(f"vibrato CC{cc} ({len(pts)} points)")
            if "dynamics" in only:
                parts_written.append(_write_lane(project, flow, pp, setup, record))
            line.append("; ".join(x for x in parts_written if x) or "nothing written")
            line.append("; ".join(pp.notes_for_log[1:]))
            report.append(" — ".join(x for x in line if x))
    if not dry_run:
        project.save(dest)
        _record_path(dest).write_text(json.dumps(record, indent=0))
        report.append(f"wrote {dest} (+ {_record_path(dest).name})")
    return report


def _scores_from_project(project: Project, src: str):
    """Model of an in-memory project (after undo) – notation is unchanged by undo, so
    read it from the file and re-attach note refs to the in-memory nodes."""
    scores = model.from_dorico_all(src)
    for sc, flow in zip(scores, project.flows()):
        refs = {}
        for inst in project.instruments(flow):
            for nr in project.notes(flow, inst):
                refs[(inst.instrument_id, nr.position, nr.pitch, nr.grace)] = nr
        for part in sc.parts:
            for n in part.notes:
                if n.ref is not None:
                    n.ref = refs.get((part.instrument_id, n.pos, n.pitch, n.grace))
        sc.flow_node = flow
    return scores


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("dest")
    ap.add_argument("--style")
    ap.add_argument("--project-file")
    ap.add_argument("--only", default=",".join(WRITES))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for line in apply(a.src, a.dest, a.style, a.project_file, tuple(a.only.split(",")), a.dry_run):
        print(line)


if __name__ == "__main__":
    main()
