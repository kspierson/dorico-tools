# dorigit reference files: dynamic modifiers, divisi changes, film

**Folder from Windows:**
`\\wsl.localhost\Ubuntu-26.04\home\ken\dev\dorico-test\dorigit\research\refs\`

Use **Dorico 5 on the PC** (the starters are Dorico 5 files). Two starter files, each a violin with 8 bars of crotchets (made by `../make_ref_starters.py` from
finale2dorico's start file; only the title differs). Add the items below and save under the names
given. If something is awkward or Dorico refuses an entry, skip it and say which. Nothing needs
exporting.

What your projects already showed (so it isn't asked again):
- **Divisi** ("Have Yourself A Merry Little Christmas"): one divisi change at bar 1 in Vln I, Vln II,
  Vla and Vc, into sections 1 and 2. Section 2 gets its own stave and voice. Unknown: what a
  return to unison and a later re-division look like, and divisi into 3 or with a soloist.
- **Film** ("BLACK LABEL"): each flow stores the video file path, frame rate (25), duration and
  two times. Markers sit in the flow's global track with text, an "important" flag, a time in
  seconds and a beat position. Unknown: which of the two times is the "flow start timecode" and
  which is the "video start offset", and what changes when the picture moves (the conform case).
- **Dynamics** (`finale2dorico/experiments/round9/ref-extras*.dorico`): fz, ffz, rfz, rffz, sfz,
  sffz, mfz, sf, subito mf-mp, messa di voce dal niente. No **modifiers** anywhere.

---

## File 1: `start-dynamics-divisi.dorico` → save as **`ref-dynamics-divisi.dorico`**

### Dynamics on the Violin, bars 1-4 (Shift+D on each beat's note, type exactly this, Enter)

| Bar | Beat 1 | Beat 2 | Beat 3 | Beat 4 | What it shows |
|---|---|---|---|---|---|
| 1 | `poco f` | `molto p` | `più f` | `meno p` | the four standard modifiers |
| 2 | `sempre mf` | `p dolce` | `mf espressivo` | `n` | sempre; free text after; niente as a dynamic |
| 3 | `sfp` | `sfzp` | `fzp` | `poco sfz` | force + level combinations; modifier on a force dynamic |
| 4 | `cresc` from beat 1 to beat 2 | | `molto dim.` from beat 3 to beat 4 | | text-style gradual dynamics (if `molto dim.` isn't accepted, skip it) |

For bar 4 beat 1: select beats 1-2, Shift+D, type `cresc`, Enter. If Dorico draws a hairpin,
change it to text in Properties > Dynamics > Gradual style "cresc." (whichever Dorico 5 offers).

### Divisi on a new section player, bars 5-8

1. Setup mode: add a **section player**, Violin (it appears below the solo violin). Leave its
   name as Dorico sets it.
2. Write mode, on the section player's staff:

| Where | What | Then enter (whole notes, one per stave) |
|---|---|---|
| bar 5 beat 1 | Write > Divisi > **Change Divisi…**: 2 sections | section 1: G5 (bar 5), A5 (bar 6); section 2: C5 (bar 5), D5 (bar 6) |
| bar 7 beat 1 | Write > Divisi > **Restore Unison** | E5 (bar 7) |
| bar 8 beat 1 | **Change Divisi…**: 3 sections, and make section 1 a **solo** if the dialog offers soloists | section 1: G5, section 2: E5, section 3: C5 |

Save as **`ref-dynamics-divisi.dorico`**.

(Later I'll make the "Vln IA changed in one version, IB in the other" pair myself from this file
and ask you only to open them.)

---

## File 2: `start-film.dorico` → save twice: **`ref-film-v1.dorico`**, then **`ref-film-v2.dorico`**

Use the BLACK LABEL picture:
`C:\Users\kspie\OneDrive\Desktop\BLACK LABEL\ETIQUETA_NEGRA_without_music.mov`.
The values are chosen to differ from each other so I can tell which field is which.

### Version 1

| Step | What |
|---|---|
| Tempo | bar 1: Shift+T `q=120`; bar 5: Shift+T `q=90` |
| Video | Setup mode > Flows panel, right-click the flow > Video > **Attach…** the .mov above |
| Video properties | same menu > **Properties…**: **flow start timecode `01:00:10:00`**, **video start offset `00:00:05:00`** (keep the frame rate Dorico picks) |
| Markers | add three markers (Play > Add Marker, or the Markers track in Play mode), entering these timecodes and texts: `01:00:12:00` "Door opens"; `01:00:14:12` "Slam", marked **important**; `01:00:20:00` "Cut to exterior" |

Save as **`ref-film-v1.dorico`**.

### Version 2 (a picture edit, as if a new cut arrived)

| Step | What |
|---|---|
| Video properties | change **video start offset to `00:00:07:00`** (picture moved by 2 seconds); leave the flow start timecode |
| Markers | move "Door opens" to `01:00:13:00`; delete "Cut to exterior"; add `01:00:18:00` "New shot" |
| Tempo | change bar 5 to `q=100` (shows whether markers keep their timecode when beats move) |

Use **File > Save As** → **`ref-film-v2.dorico`** (keep v1 as it is).

---

## Results

### `ref-dynamics-divisi.dorico` (arrived 2026-10-30)

You laid it out as a ladder on the Violin (bars 1-4) and put the divisi on the same Violin
(bars 5-8). dorigit's listing reads every dynamic in it by name.

**Dynamics:**
- Modifiers are two numbered slots in `intensityModifier`: amount **2 = poco, 4 = molto**, then
  **1 = meno, 2 = più** (mapping confirmed by you). Listed as "poco ppppp", "più mf"; both slots
  together read "poco meno f" (seen in the Rite of Spring).
- **Possibile** is standard in Dorico, but only on f or p (your correction). p possibile is
  `{int: 1}, {int: 1}, …`, f possibile `{int: 0}, {int: 1}, …`.
- Subito on any level; 6 letters (pppppp/ffffff) is the range Dorico offers.
- Not asked again: sempre, free text after a dynamic (dolce, espressivo), niente as a dynamic,
  sfp/sfzp/fzp. If they ever appear they stay readable ("custom dynamic …" or
  "(modifier …)"), never dropped.

**Divisi** (`DivisiEventDefinition` in the stave stream):

| Bar | Event | Stored as |
|---|---|---|
| 5 | divide into 2 | `sections`: two `section`s labelled "1", "2"; `soloists` empty |
| 7 | **unison** | the same event type with `sections` and `soloists` **empty** |
| 8 | Solo + gli altri | one `soloist` labelled "Solo", one `section` labelled "gli altri" |

Dorico makes **one** extra stave (`divisiIndex` 0, its own voice) and reuses it for each later
division. Section 2 / "gli altri" notes are in that voice. A merge region is therefore (stave or
divisi stave, bar range between divisi events), and an IA-vs-IB edit pair lands in different
voices, so it can be told apart automatically.

### `ref-film-v1.dorico` / `ref-film-v2.dorico` (arrived 2026-10-31)

You made your own scenario: `start-film.dorico` (saved over the starter) became a "v0" with
markers at 4 s (important) and 8 s and tempos 62 → 94 at bar 3; v1 moved them to 5 s and 10 s
and added "Something Important" at 15 s; v2 changed the video settings, renamed/moved/deleted/
added markers and changed the bar-3 tempo to 102. (v1 was saved a minute after v2; the diff
header shows that, harmlessly.)

**Video** (`flow/flowVideoData`), confirmed by you on v2:

| Field | Meaning | v2 |
|---|---|---|
| `videoAttachmentPosition` | where the picture starts in the flow (crotchets) | 4 = bar 2 beat 1 |
| `kVideoEventInTime` | video start offset: seconds into the clip | 6 |
| `kVideoClipTimecodeStart` | timecode of the clip's first frame (seconds) | 3600 = 01:00:00:00 |
| `kVideoClipDuration`, `kVideoClipFrameRate` | clip length, fps | 500, 25 |

**Markers** (`MarkerEventDefinition`, global stream):
- `timePosition` is **clip time** in seconds. Dorico shows it as timecode start + clip time
  (you confirmed "Something Important" = 01:00:21:00 in v2).
- `position` (beats) is **derived**: in v2 all three markers sit 2.129 s later in the clip
  than in the music (6 s offset − 3.871 s for bar 2 beat 1 at 62 bpm), and after the tempo
  change to 102 their beat positions were recomputed while their times stayed. So **markers
  follow the picture, not the music**: exactly what conforming needs.
- An edited marker keeps its `eventID` (34 "5 Seconds In" → "8 Seconds In"); deleted ones
  vanish, new ones get new IDs. dorigit can track a marker across cuts by ID.
- Tempo: `tempoValue` is microseconds per crotchet (967741 = 62 bpm).

What dorigit shows now (listing and diff, 2026-10-31):

```
Flow: dorigit ref 2: film  (6 changes)
  ~ video: ETIQUETA_NEGRA_without_music.mov at bar 1 beat 1, clip from 00:00:00:00 (timecode 00:00:00:00), 25 fps
        -> ETIQUETA_NEGRA_without_music.mov at bar 2 beat 1, clip from 00:00:06:00 (timecode 01:00:06:00), 25 fps
  (global)
    + bar 1 beat 1+431/480 added marker "3s CUE" at 01:00:03:00
    ~ bar 2 beat 3+1/15 marker: moved bar 2 beat 2+1/6 -> bar 2 beat 3+1/15, "5 Seconds In" at 00:00:05:00 -> "8 Seconds In" at 01:00:08:00
    + bar 3 beat 1 added tempo 102 bpm
    - bar 3 beat 1 removed tempo 94 bpm
    - bar 3 beat 4+43/80 removed marker "10 Seconds In" at 00:00:10:00
    ~ bar 7 beat 3+147/160 marker: moved bar 5 beat 4+89/240 -> bar 7 beat 3+147/160, …
```

Still unverified: drop-frame rates (29.97 DF), and BLACK LABEL's displayed timecodes (decoded the
same way, e.g. 1m1 "Walk Away" at 01:02:04:24).
