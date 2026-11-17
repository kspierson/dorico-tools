"""Standard MIDI File reader: moved to the shared engine (`doricokit.midi`, 2026-11-01).

Kept as a re-export so existing imports (`from doricohp import smf`) work unchanged.
"""
from doricokit.midi import CtrlEv, Midi, NoteEv, read  # noqa: F401
from doricokit.midi import _vlq  # noqa: F401  (kept for any old callers)
