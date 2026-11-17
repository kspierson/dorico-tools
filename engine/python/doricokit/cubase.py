"""Cubase track archives: generate instrument tracks (plug-in state + one MIDI part) to import.

Cubase 13's File > Export > Selected Tracks writes a `<tracklist2>` XML "track archive"; File >
Import > Track Archive reads it back. This module clones the instrument tracks of a sample archive
the user exported once (two Kontakt 7 instrument tracks, `data/cubase13-kontakt7-tracks.xml.gz`,
plug-in states stripped) and fills in, per track: name, plug-in state, preset label and MIDI.

    from doricokit import cubase, virender as vr
    arc = cubase.TrackArchive()                        # the bundled Kontakt 7 template
    arc.add("HP s09 LASS", component=st.kontakt7_state(), label="HP s09",
            events=[cubase.cc(0.0, 0, 11, 75), cubase.note(1.0, 0, 60, 90, 0.5)])
    arc.write("round1.xml")

Format notes (worked out from the user's export, 2026-11-01):
  - objects carry `ID="n"`; later references are `<obj name=".." ID="n"/>` (IDs only need to be
    unique in the file). The first track defines the Tempo/Signature tracks the others refer to;
    MediaBay settings live in top-level objects after the track list.
  - MIDI: 480 ticks per quarter; `MMidiNote`/`MMidiController` Start (ticks, part-relative),
    Channel (0-based, omitted for 0), Data1/Data2, HrData = the value as 0..1 (v/128 up to 64,
    0.5 + (v-64)/126 above).
  - the instrument is `<member name="Synth Slot">`: Plugin UID GUID (VST3 class id), Plugin Name,
    `<bin name="audioComponent">` = the component state in hex (for Kontakt 7 the same bytes as
    Dorico's enginedata "Comp" chunk), "Bay Program" = preset name shown.
"""
from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["TrackArchive", "Event", "cc", "note", "make_template", "TEMPLATE", "TICKS_PER_QUARTER"]


TEMPLATE = Path(__file__).with_name("data") / "cubase13-kontakt7-tracks.xml.gz"
TICKS_PER_QUARTER = 480
KONTAKT7_GUID = "5653544E694B376B6F6E74616B742037"

_TRACK = re.compile(r'(?ms)^      <obj class="(\w+)" ID="(\d+)">\n.*?^      </obj>\n')
_TOP = re.compile(r'(?ms)^   <obj class="(\w+)"(?: name="[^"]*")? ID="(\d+)">\n.*?^   </obj>\n')
_DEF = re.compile(r'<obj class="[^"]+"[^>]*? ID="(\d+)"')
_REF = re.compile(r'<obj name="[^"]*" ID="(\d+)"/>')


@dataclass
class Event:
    t: float          # seconds from the part start (tempo 120: 960 ticks per second)
    kind: str         # "cc" | "note"
    channel: int      # 0-based
    data1: int
    data2: int
    dur: float = 0.0  # notes: seconds


def cc(t: float, channel: int, number: int, value: int) -> Event:
    return Event(t, "cc", channel, number, value)


def note(t: float, channel: int, pitch: int, velocity: int, dur: float) -> Event:
    return Event(t, "note", channel, pitch, velocity, dur)


def _hr(v: int) -> str:
    return repr(v / 128 if v <= 64 else 0.5 + (v - 64) / 126)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _hex_bin(data: bytes, indent: str) -> str:
    h = data.hex().upper()
    rows = "".join("\t" * 8 + h[i:i + 64] + "\n" for i in range(0, len(h), 64))
    return "\n" + rows + indent


def make_template(sample_archive: str | Path, out: str | Path = TEMPLATE) -> None:
    """Store a user-exported archive (>= 2 instrument tracks) as the template, minus the
    instrument states (they are the user's; every generated track gets its own)."""
    s = Path(sample_archive).read_text(encoding="utf-8")
    out_parts, pos = [], 0
    for m in re.finditer(r'<member name="Synth Slot">', s):
        b = s.index('<bin name="audioComponent">', m.end()) + len('<bin name="audioComponent">')
        e = s.index("</bin>", b)
        out_parts += [s[pos:b], "\n" + " " * 21]
        pos = e
    out_parts.append(s[pos:])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(gzip.compress("".join(out_parts).encode("utf-8")))


class TrackArchive:
    def __init__(self, template: str | Path = TEMPLATE):
        p = Path(template)
        raw = p.read_bytes()
        s = (gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw).decode("utf-8")
        open_tag = '<list name="track" type="obj">\n'
        a = s.index(open_tag) + len(open_tag)
        b = s.index("\n   </list>\n", a) + 1
        self.head, self.tracks_src, rest = s[:a], [m.group(0) for m in _TRACK.finditer(s, a, b)], s[b:]
        if len(self.tracks_src) < 2:
            raise ValueError("template needs two instrument tracks (the first defines the tempo track)")
        self.list_close = "   </list>\n"
        self.top = {m.group(2): m.group(0) for m in _TOP.finditer(rest)}
        self.top_order = list(self.top)
        refs = [set(_REF.findall(t)) for t in self.tracks_src]
        # top-level objects only the clone source (track 2) uses are cloned with it
        self.own = [r & set(self.top) - set().union(*(x for j, x in enumerate(refs) if j != i))
                    for i, r in enumerate(refs)]
        self.used_ids = set(re.findall(r'ID="(\d+)"', s))
        self.next_id = 100_000_000
        self.out_tracks: list[str] = []
        self.out_top: list[str] = []

    def _new_id(self) -> str:
        while str(self.next_id) in self.used_ids:
            self.next_id += 1
        self.used_ids.add(str(self.next_id))
        return str(self.next_id)

    def _events_xml(self, events: list[Event], indent: str) -> str:
        out = []
        tick = lambda sec: int(round(sec * TICKS_PER_QUARTER * 2))  # tempo 120
        order = sorted(events, key=lambda e: (e.t, e.kind != "cc"))
        i2 = indent + "   "
        for e in order:
            cls = "MMidiController" if e.kind == "cc" else "MMidiNote"
            L = [f'{indent}<obj class="{cls}" ID="{self._new_id()}">',
                 f'{i2}<float name="Start" value="{tick(e.t)}"/>']
            if e.channel:
                L.append(f'{i2}<int name="Channel" value="{e.channel}"/>')
            L += [f'{i2}<int name="Data1" value="{e.data1}"/>', f'{i2}<int name="Data2" value="{e.data2}"/>',
                  f'{i2}<float name="HrData" value="{_hr(e.data2)}"/>',
                  f'{i2}<int name="PreNoteOn" value="0"/>', f'{i2}<int name="OneShotDef" value="0"/>']
            if e.kind == "note":
                L += [f'{i2}<float name="Length" value="{max(1, tick(e.t + e.dur) - tick(e.t))}"/>',
                      f'{i2}<int name="Data3" value="64"/>', f'{i2}<int name="pitchFlags" value="32"/>',
                      f'{i2}<float name="OffVelocity" value="0.5"/>']
            L.append(f"{indent}</obj>")
            out.append("\n".join(L) + "\n")
        return "".join(out)

    def add(self, name: str, component: bytes, events: list[Event], label: str = "") -> None:
        """One instrument track: the template's plug-in (Kontakt 7) with this component state,
        and one MIDI part from bar 1 holding `events` (any channels)."""
        first = not self.out_tracks
        k = 0 if first else 1
        own = [self.top[i] for i in self.top_order if i in self.own[k]]
        block = self.tracks_src[k]
        if not first:
            # clones: new IDs for every object defined in the track or its own top-level objects;
            # references to the first track's Tempo/Signature tracks keep theirs
            ids = set(_DEF.findall(block)) | {i for t in own for i in _DEF.findall(t)}
            mp = {i: self._new_id() for i in ids}
            sub = lambda t: re.sub(r'ID="(\d+)"', lambda m: f'ID="{mp.get(m.group(1), m.group(1))}"', t)
            block, own = sub(block), [sub(t) for t in own]
        old = re.search(r'<string name="Name" value="([^"]*)"', block).group(1)
        block = block.replace(f'value="{old}"', f'value="{_esc(name)}"')
        # the instrument: state, preset label, instance id
        ss = block.index('<member name="Synth Slot">')
        b = block.index('<bin name="audioComponent">', ss) + len('<bin name="audioComponent">')
        e = block.index("</bin>", b)
        block = block[:b] + _hex_bin(component, block[block.rindex("\n", 0, e) + 1:e]) + block[e:]
        block = block[:ss] + re.sub(r'<string name="Bay Program" value="[^"]*"',
                                    lambda m: f'<string name="Bay Program" value="{_esc(label or name)}"',
                                    block[ss:], count=1)
        block = re.sub(rf'"({KONTAKT7_GUID}-)\d+"', lambda m: f'"{m.group(1)}{100 + len(self.out_tracks)}"', block)
        # the MIDI part: its events, its length, the track's length
        end_s = max([ev.t + ev.dur for ev in events] + [1.0])
        part_ticks = (int(end_s * 2 * TICKS_PER_QUARTER) // 1920 + 2) * 1920
        mpart = block.index('class="MMidiPart"')
        lo = block.index('<list name="Events" type="obj">', mpart)
        ind = block[block.rindex("\n", 0, lo) + 1:lo]
        lo_end = lo + len('<list name="Events" type="obj">\n')
        hi = block.index("\n" + ind + "</list>", lo_end) + 1
        block = block[:lo_end] + self._events_xml(events, ind + "   ") + block[hi:]
        pe = block.rindex('class="MMidiPartEvent"', 0, mpart)
        block = block[:pe] + re.sub(r'(<float name="Length" value=")[^"]*', rf"\g<1>{part_ticks}", block[pe:], count=1)
        block = re.sub(r'(<float name="Length" value=")[^"]*', lambda m: m.group(1) + str(max(576000, part_ticks + 3840)),
                       block, count=1)  # first Length in the block = the track event's
        self.out_tracks.append(block)
        if not first:
            self.out_top.extend(own)

    def write(self, path: str | Path) -> None:
        if not self.out_tracks:
            raise ValueError("no tracks added")
        # the template's top-level objects (shared + the first track's) in their order, then the clones'
        base = [self.top[i] for i in self.top_order if i not in self.own[1]]
        text = self.head + "".join(self.out_tracks) + self.list_close + "\n".join(base + self.out_top) + "</tracklist2>\n"
        Path(path).write_text(text, encoding="utf-8", newline="\n")
