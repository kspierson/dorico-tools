"""Standard MIDI Files: read and write (standard library only). The `midi` module of
PLANNED_WORK.md §2.3 (Python first; Rust in S9).

    from doricokit import midi
    m = midi.read("capture.mid")            # notes (paired on/off), controllers, tempo map
    m.seconds(tick); m.tick(seconds)        # tempo map, both ways
    m.bar_start(14); m.tick_at(28, 9/2)     # bar numbers from the time signatures (bar 1 = tick 0)
    midi.write("out.mid", tracks, ppq=m.ppq, tempos=m.tempos, time_sigs=m.time_sigs)

The reader came from dorico-hp (`doricohp/smf.py`, now a re-export of this module) unchanged.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["NoteEv", "CtrlEv", "Midi", "Track", "read", "write"]


@dataclass
class NoteEv:
    track: int
    channel: int
    pitch: int
    velocity: int
    start: int  # ticks
    end: int
    off_velocity: int = 64

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class CtrlEv:
    track: int
    channel: int
    kind: str      # "cc", "pitchbend", "program", "aftertouch"
    number: int    # controller number (cc) / program
    value: int
    tick: int


@dataclass
class Midi:
    ppq: int
    format: int
    notes: list[NoteEv] = field(default_factory=list)
    ctrls: list[CtrlEv] = field(default_factory=list)
    tempos: list[tuple[int, int]] = field(default_factory=list)  # (tick, microseconds per crotchet)
    track_names: dict[int, str] = field(default_factory=dict)
    time_sigs: list[tuple[int, int, int]] = field(default_factory=list)  # (tick, num, den)

    def seconds(self, tick: int) -> float:
        """Convert a tick to seconds using the tempo map."""
        tempos = self.tempos or [(0, 500000)]
        t, last_tick, us = 0.0, 0, 500000
        for tk, tempo in tempos:
            if tk >= tick:
                break
            t += (tk - last_tick) * us / self.ppq / 1e6
            last_tick, us = tk, tempo
        return t + (tick - last_tick) * us / self.ppq / 1e6

    def tick(self, seconds: float) -> int:
        """The tick sounding at `seconds` (inverse of `seconds`), rounded to the nearest tick."""
        t, last_tick, us = 0.0, 0, 500000
        for tk, tempo in self.tempos or [(0, 500000)]:
            seg = (tk - last_tick) * us / self.ppq / 1e6
            if t + seg > seconds:
                break
            t += seg
            last_tick, us = tk, tempo
        return last_tick + round((seconds - t) * 1e6 * self.ppq / us)

    def bpm_at(self, tick: int) -> float:
        us = 500000
        for tk, tempo in self.tempos:
            if tk > tick:
                break
            us = tempo
        return 60e6 / us

    def bar_start(self, bar: int) -> int:
        """Tick where `bar` starts. Bar 1 starts at tick 0 (no pick-up handling); bars are
        laid out from the time signatures, 4/4 before the first one."""
        sigs = sorted(self.time_sigs) or [(0, 4, 4)]
        tick, i = 0, 0
        for _ in range(bar - 1):
            while i + 1 < len(sigs) and sigs[i + 1][0] <= tick:
                i += 1
            _, num, den = sigs[i]
            tick += num * self.ppq * 4 // den
        return tick

    def tick_at(self, bar: int, crotchets: float = 0) -> int:
        """Tick of a position given as a bar plus crotchets from its start."""
        return self.bar_start(bar) + round(crotchets * self.ppq)


def _vlq(data: bytes, p: int) -> tuple[int, int]:
    v = 0
    while True:
        b = data[p]
        p += 1
        v = (v << 7) | (b & 0x7F)
        if b < 0x80:
            return v, p


def read(path: str | Path) -> Midi:
    data = Path(path).read_bytes()
    if data[:4] != b"MThd":
        raise ValueError(f"{path}: not a MIDI file")
    hlen = struct.unpack(">I", data[4:8])[0]
    fmt, ntrk, div = struct.unpack(">HHH", data[8:14])
    if div & 0x8000:
        raise ValueError("SMPTE time division not supported")
    m = Midi(div, fmt)
    p = 8 + hlen
    for tr in range(ntrk):
        if data[p:p + 4] != b"MTrk":
            raise ValueError(f"bad track header at {p}")
        tlen = struct.unpack(">I", data[p + 4:p + 8])[0]
        q, end = p + 8, p + 8 + tlen
        tick, status = 0, 0
        open_notes: dict[tuple[int, int], list[tuple[int, int]]] = {}
        while q < end:
            delta, q = _vlq(data, q)
            tick += delta
            b = data[q]
            if b & 0x80:
                status = b
                q += 1
            if status == 0xFF:
                mtype = data[q]
                ln, q = _vlq(data, q + 1)
                payload = data[q:q + ln]
                q += ln
                if mtype == 0x51:
                    m.tempos.append((tick, int.from_bytes(payload, "big")))
                elif mtype == 0x03:
                    m.track_names[tr] = payload.decode("latin-1")
                elif mtype == 0x58:
                    m.time_sigs.append((tick, payload[0], 2 ** payload[1]))
                continue
            if status in (0xF0, 0xF7):
                ln, q = _vlq(data, q)
                q += ln
                continue
            kind, ch = status & 0xF0, status & 0x0F
            if kind in (0xC0, 0xD0):
                v = data[q]
                q += 1
                m.ctrls.append(CtrlEv(tr, ch, "program" if kind == 0xC0 else "aftertouch", v if kind == 0xC0 else 0, v, tick))
                continue
            a, b2 = data[q], data[q + 1]
            q += 2
            if kind == 0x90 and b2 > 0:
                open_notes.setdefault((ch, a), []).append((tick, b2))
            elif kind == 0x80 or (kind == 0x90 and b2 == 0):
                stack = open_notes.get((ch, a))
                if stack:
                    st, vel = stack.pop(0)
                    m.notes.append(NoteEv(tr, ch, a, vel, st, tick, b2 if kind == 0x80 else 64))
            elif kind == 0xB0:
                m.ctrls.append(CtrlEv(tr, ch, "cc", a, b2, tick))
            elif kind == 0xE0:
                m.ctrls.append(CtrlEv(tr, ch, "pitchbend", 0, (b2 << 7 | a) - 8192, tick))
            elif kind == 0xA0:
                m.ctrls.append(CtrlEv(tr, ch, "polyaftertouch", a, b2, tick))
        p = end
    m.notes.sort(key=lambda n: (n.start, n.pitch))
    m.ctrls.sort(key=lambda c: c.tick)
    m.tempos.sort()
    return m


# --- writing -------------------------------------------------------------------------------


@dataclass
class Track:
    """One output track: notes are (start tick, pitch, velocity, length in ticks); controllers are
    (tick, controller number, value) and go before notes at the same tick."""
    name: str = ""
    notes: list[tuple[int, int, int, int]] = field(default_factory=list)
    channel: int = 0
    program: int | None = None
    ctrls: list[tuple[int, int, int]] = field(default_factory=list)


def _vlq_bytes(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def _chunk(events: list[tuple[int, int, bytes]]) -> bytes:
    """events: (tick, order, bytes); at equal ticks lower `order` first (note-offs before ons)."""
    body, last = bytearray(), 0
    for tick, _, ev in sorted(events, key=lambda e: (e[0], e[1])):
        body += _vlq_bytes(tick - last) + ev
        last = tick
    body += b"\x00\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def write(path: str | Path, tracks: list[Track], *, ppq: int = 960,
          tempos: list[tuple[int, int]] | None = None,
          time_sigs: list[tuple[int, int, int]] | None = None, single_track: bool = False) -> None:
    """Write a format-1 file: a conductor track (tempos, time signatures), then `tracks`.
    single_track: format 0 instead, everything merged into one track (channels kept), so a DAW
    imports one multi-channel part (Cubase splits format-1 files into one track per track)."""
    conductor: list[tuple[int, int, bytes]] = []
    for tick, us in tempos or [(0, 500000)]:
        conductor.append((tick, 0, b"\xff\x51\x03" + us.to_bytes(3, "big")))
    for tick, num, den in time_sigs or []:
        conductor.append((tick, 0, bytes([0xFF, 0x58, 4, num, den.bit_length() - 1, 24, 8])))
    per_track: list[list[tuple[int, int, bytes]]] = []
    for t in tracks:
        ch = t.channel & 0x0F
        evs: list[tuple[int, int, bytes]] = []
        if t.name and not single_track:
            name = t.name.encode("latin-1", "replace")
            evs.append((0, 0, b"\xff\x03" + _vlq_bytes(len(name)) + name))
        if t.program is not None:
            evs.append((0, 1, bytes([0xC0 | ch, t.program & 0x7F])))
        for tick, num, value in t.ctrls:
            evs.append((tick, 1, bytes([0xB0 | ch, num & 0x7F, max(0, min(127, value))])))
        for start, pitch, vel, length in t.notes:
            evs.append((start, 3, bytes([0x90 | ch, pitch & 0x7F, max(1, min(127, vel))])))
            evs.append((start + max(1, length), 2, bytes([0x80 | ch, pitch & 0x7F, 64])))
        per_track.append(evs)
    if single_track:
        chunks = [_chunk(conductor + [e for evs in per_track for e in evs])]
    else:
        chunks = [_chunk(conductor)] + [_chunk(evs) for evs in per_track]
    header = b"MThd" + struct.pack(">IHHH", 6, 0 if single_track else 1, len(chunks), ppq)
    Path(path).write_bytes(header + b"".join(chunks))
