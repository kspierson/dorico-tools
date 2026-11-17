Project S check files (2026-10-29). Please open each in Dorico 5 and say whether it opens normally.

These are the first .dorico files written by the shared engine's Rust zip writer (S2). The
contents of every file inside the zip are identical to what the old Python code wrote (checked
automatically); only the zip packaging differs. dorico-hp's Apply now uses this writer, so this
confirms future listening copies will open.

S2-1 rewrite A (no change).dorico   test file A, decoded and rewritten with no edits
S2-2 Apply on A (Standard).dorico   dorico-hp Apply (Standard style) on test file A

Open from Windows at:
\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\engine\tests\dorico-check\


Timeline reference (2026-10-31) - timeline-ref.dorico
======================================================
Made by make_timeline_ref.py. It pins down how Dorico times playback (rit./accel. curves,
fermatas, repeats, metric modulation, default tempo) so the engine's timeline can be checked
against Dorico's own MIDI export. One flute; every bar has its own pitch.

Flows: 1 Tempo kinds, 2 Rit and accel, 3 Fermatas, 4 Repeats D.S., 5 D.C. al Fine,
6 No tempo, 7 For you to add.

Steps (about 10 minutes):
 1. Open timeline-ref.dorico in Dorico 5. Tell me if anything looks wrong.
 2. Flow "7 For you to add" - add with the tempo popover (Shift+T), each on beat 1:
      bar 3: meno mosso        bar 5: a tempo        bar 9: tempo primo
      bars 10-11: rit.  (select bars 10-11 first), then in Properties set Final tempo % = 50
 3. Flow "4 Repeats D.S.": select the end-repeat barline (end of bar 4) and set it to play
    3 times (Properties panel, Repeat barlines / play count).
 4. File > Save.
 5. If Dorico lets you without a video: Play mode > Play > Video > Video Properties,
    set Project frame rate to 29.97 dfps, then File > Save As... timeline-ref-2997df.dorico
    (skip if the option isn't there).
 6. File > Export > MIDI... from timeline-ref.dorico, all flows, one file per flow if offered,
    into a new folder here: timeline-ref-midi
 7. Optional, same export (MIDI) for:
      engine\tests\dorico-files\reference\bars-numbers-repeats.dorico  (your repeats file)
      engine\tests\dorico-files\ET The Flying Theme mASTER A-rebuilt.dorico  (real rit. data)
    into timeline-ref-midi as well.

Result (2026-11-01): your exports match the engine's timeline event for event (9 flows).
Details and what is still open: engine/docs/TIMELINE.md.
