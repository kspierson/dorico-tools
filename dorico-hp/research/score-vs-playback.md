# Score versions vs playback versions: what the user changed for playback

The user's working method was a balanced "score" version plus "playback" versions with
markings re-voiced for specific libraries. The difference is what the notation alone
does not tell a VI, and so what the HP rebuild has to supply (as playback-only data) so
that one score can serve both purposes.

Tools: `tools/compare_versions.py` (per-instrument diff of performance markings: dynamic
level at every note, dynamics/hairpins added/removed, articulation changes on the same
notes, notes added/removed), `tools/marking_context.py` (where articulations were added),
`doricohp/notation.py` (Dorico reader; Finale via finale2dorico's `f2d ir`).
Full reports: `research/score-vs-playback/`.

## Pairs examined

| score version | playback version | libraries | notes |
|---|---|---|---|
| `VV_Full.mus` (Virtus Vitae 1m1, Finale 2012) | `VV_Full BR.mus` | SWAM brass | only brass re-voiced |
| `VV_Full.mus` | `VV_Full STR.mus` | LASS 2.5 strings (+ woodwinds, harp, timpani changed too) | brass untouched |
| `HP - birds.dorico` (≈ original) | `Harry Potter Cues Plus 5 + LASS3.dorico`, flow "Rainy Nights, Dementors and Birds" | LASS 3 + others | playback version is also re-orchestrated (≈40 extra players, rewritten string parts); only the 7 shared instruments compared |

Not compared yet: `VV1m2*` drafts, `BLACK LABEL - short.dorico` (no score version; it has
hand-made timing offsets, see below).

Only notes present in both versions (same position and pitches) are compared, so
re-orchestration and recomposition don't count as playback changes.

## What changed

**1. Section balance (per library / instrument).** The dynamic level in force at each
note moves by a fairly constant amount per instrument:

| version | instrument | mean shift (steps, mf→f = 1) |
|---|---|---|
| VV STR | violins / viola | +1.0 … +1.25 |
| VV STR | cello / bass | +0.7 … +0.8 |
| VV STR | clarinets | +1.5 … +1.7 |
| VV STR | harp | −2.8 |
| VV STR | tuba | −0.6 |
| VV BR | trombones / trumpet 2 | +0.9 … +1.1 |
| HP LASS3 | viola | +1.3 |
| HP LASS3 | cello | −1.7 |

→ a **level offset per library/instrument profile**, applied through Dorico's dynamics
lane; no change to the written dynamics.

**2. Range stretching at the ends.** Peaks pushed up (ff → ffff in VV strings at bar 27,
ff → ffff cello/bass bar 1) and quiet entries lifted for brass (ppp → p at bar 5 for every
VV brass part). HP strings go the other way in soft passages (pp → pppp).
→ a **per-library dynamic curve** (how notated levels map onto the library's range).
Dorico already has part of this: the expression map's dynamic range (`velocityRange`)
and `dynamicCurveParams`; the profile can use those first and the lane for the rest.

**3. Phrase swells.** Many hairpins added that the score doesn't have: VV STR +105 / −41,
VV BR +60 / −32, HP +8 / −6. Two kinds:
- phrase-length arches (HP flute 1: cresc. over bar 21, dim. bar 22; mp < ff > mf over
  bars 31–33),
- short swells into a note (VV: crescendos lasting a beat or less before a downbeat).
→ **phrase shaping rules** (the part Finale HP never did, see hp-engine.md: CC11 flat on
unmarked music). Needs a closer look at where the arches sit (slur groups, pitch peaks,
phrase ends) before writing the rule.

**4. Accents written as dynamic spikes.** pppp → ffffff → ppp inside one beat (HP flute
2, bar 24), sfz → sffz (VV trumpets), added ffff hits. → **accent depth per library**
(how far an accent/sfz pushes the dynamic), applied in the dynamics lane around the note.

**5. Articulations swapped to pick samples or lengths.**
- VV STR (strings + woodwinds): tenuto added to 730 notes, mostly fast semiquavers
  (22 % of all ≤ semiquaver notes) and off-beats; accents 290, marcatos 210;
  staccatissimo → staccato 80 (woodwinds).
- VV BR: marcato 95, accent+tenuto 55, tenuto 31, mostly crotchets/minims after rests and
  on beats; horn slurs 1 → 15.
- HP LASS3: staccato → staccatissimo 31 (flute), accents added.
These look like patch/length selection (sustain patch for runs, short patch for detached
notes, harder attack for brass entries) rather than phrasing. → In Dorico these belong to
the **expression map** (technique conditions such as LASS 3's
`NoteLength <= kVeryShort` for staccato, and length/velocity factors) and **playback
options** (articulation lengths, which the maps already override per library). Apply
only adds per-note attack (velocity) and length where the map can't express it.

**6. Hand-made timing offsets (Black Label).** The shaker/cowbell/triangle/guiro player
has 168 notes moved earlier by 3–35 ticks (≈ 20–35 ms at 123 bpm), start and end
together, slightly varied. → **per-library start offset with small variation**
(latency compensation + humanise), as planned in `dorico-integration.md`.

**7. No hidden markings.** None of the Dorico projects uses hidden dynamics or
techniques, nor Play-mode data apart from the Black Label offsets: everything was done
by changing visible notation. That is the gap: the same intentions must become
playback-only data.

## Second batch (HPCaptures\finale: rod, ww, willow, fanfare, midi)

Reports: `research/score-vs-playback/` (`ww.md`, `willow.md`, `fanfare.md`, `rod-ds.md`,
`fantasia-midi.md`, `willow-midi-*.md`).

| files | what they turned out to be |
|---|---|
| `wworch.mus` / `wworch_pb.mus` | Identical notation. After conversion to .musx: the pb copy plays through **Kontakt 5** instead of SmartMusic SoftSynth + Garritan Ambience, and switches HP from **Standard to 21st Century** (same accents/feel/rubato; turns off softenBasses, adjustDottedEighth, interpretCadences; turns on final-bar rit. and auto-pedalling). No MIDI-tool or controller edits. So this "playback score" = different instruments + a different HP style. |
| `Willow I.mus` / `Willow Prep.mus` | Same markings; hairpins only moved slightly (129 added / 121 removed = repositioned); same HP style (Standard) and plug-ins (KontaktPlayer2 + Garritan Ambience), no MIDI-tool edits. Print preparation, not playback. |
| `fanfare.mus` / `fanfare pb.mus` | Different versions of the piece (34 vs 50 bars; 55 of 152 trumpet notes match). Trumpet one step softer in the pb copy. Limited use. |
| `reign of death*.musx` | Section files (brass, ww, perc, rhythm "ds") plus `_str` = full score: stems for playback, not score/playback pairs. `_ds` = base minus 4 drum dynamics. Brass file holds 638 per-bar CC100 sends (SWAM mute control); ww file one note with a MIDI-tool velocity. |
| `fantasia.mid` / `fantasia_playback.mid` | Same music, HP on, matched within 1/8 beat: the playback copy has the **low instruments much softer** (velocity: tuba −20, bass clarinet −18, bassoon −12, cello −10, horns/trombones −10, viola −6), timpani +10, upper woodwinds/strings −1…−3. Same balance habit as finding 1, done by velocity. |
| `willow exp/vel.mid`, `Willow FULL/GPO.mid` | One score, HP rendered for different devices: dynamics on CC11 (exp, FULL), CC7 (vel) or **CC1 for Garritan GPO** (+ CC68 legato, CC21). Same velocities for exp/vel/FULL; for GPO the controller uses the full range (0–119 vs 29–102 on CC11), velocities are reshaped per note (sd ≈ 18) and notes play 4–8 % shorter. |

**What this adds:**
- **Finale HP itself already had per-device profiles** (Garritan: CC1 with a wider curve,
  CC68 legato, different velocities and lengths). The library-profile layer in the
  rebuild is the same idea, generalised and editable.
- **Bass softening and low-brass/woodwind balance** is the most consistent thing the user
  did by hand (VV harp/tuba, HP cello, fantasia tuba/bassoon/bass clarinet/cello).
  HP has `softenBasses` (on in Standard, Classical, Romantic…), but it evidently wasn't
  enough for these libraries → a stronger, per-library "bass balance" parameter.

## Phrase swells: where the added hairpins sit

`tools/swell_context.py` → `research/score-vs-playback/swells-*.md` (with every hairpin
listed). Added = no hairpin of the same direction within 1/2 crotchet in the score copy.

| context | VV STR cresc/dim | VV BR cresc/dim | HP LASS3 cresc/dim |
|---|---|---|---|
| total added | 60 / 21 | 39 / 14 | 4 / 4 |
| with the melodic contour (cresc rising, dim falling) | 31 / 4 | 6 / 1 | 4 / 3 |
| inside one slur | 25 / 1 | 1 / 0 | 0 / 1 |
| starts at a slur start | 22 / 1 | 1 / 0 | 1 / 1 |
| crescendo into an arrival (ends on a beat, onto a longer/higher note) | 17 | 21 | 0 |
| on one held note (swell/fade) | 6 / 7 | 13 / 6 | 0 |
| diminuendo to a phrase end (rest/slur end follows) | 8 | 6 | 0 |
| arch (< directly followed by >) | 1 / 1 | 0 | 2 / 1 |
| length ≤ 2 crotchets / longer | 37 / 23 cresc | 15 / 24 cresc | all ≤ 2 |

Four habits, which line up with known expressive-performance rules (KTH "phrase arch",
"high loud", "final ritard / phrase-end release"):

1. **Rise-swell** (strings, woodwinds): a crescendo across a rising slurred group,
   starting at the slur, 1–4 crotchets long.
2. **Arrival crescendo** (brass most, strings too): crescendo over the last beats before a
   longer or higher note on a beat.
3. **Held-note swell** (brass): crescendo through a sustained note, usually into the next
   entry; the mirror case is a fade on a held note.
4. **Phrase-end release**: diminuendo on the last note(s) before a rest or slur end.

Crescendos outnumber diminuendos about 3 : 1; the playback copies mostly add *motion
into* notes. These become the phrase-shaping rules, each with a depth per style and per
library (brass: more held-note swell and arrival; strings/woodwinds: more rise-swell),
written into Dorico's dynamics lane.

## Printed score vs the user's Dorico versions: HP flute solo

Images of the published (condensed) score: `HPCaptures\images\hp-flute\1-4.png`, print bars
129–150 = Dorico "Rainy Nights, Dementors and Birds" bars 19–40 (print = Dorico + 110).

| | printed | "HP - birds" (≈ original) | LASS3 playback copy |
|---|---|---|---|
| runs (32nds, 16ths) | **"mf stacc., brillante"** written once at 129; most notes without dots | staccato dot on every note | dots on every note; 16ths → staccatissimo |
| accents | only at group starts / high points (C6 b130 slur start, A6 b132 and b142, G6 b140, peaks later) | all 8 notes of b21 (=131) accented | accent + staccatissimo |
| slurs | as printed (pairs, the long slur 130–131, the 2. cue slur) | same | same |
| dynamics | mf at 129, cresc. in 130 … mf at 146 | + ffff spike b24 | + swells b21–22, mp<ff>mf b31–33 |

What the playback edits achieve, measured in time (80 bpm, flute = SWAM with the map's
staccato 38 % / staccatissimo 19 %): run notes play **~36 ms** (32nd × 38 % or 16th × 19 %),
separated notes **~71 ms**. So the intended "brillante" staccato is a fixed short time, not
a percentage of the written value.

Rules this suggests (beyond HP and Dorico):
1. **Passage articulation words carry over.** "stacc.", "staccato", "leggiero", "spiccato",
   "brillante", "marcato", "legato", "sempre …" set the default articulation/character of
   the following notes (unslurred notes for stacc.) until another such word, "ord.", or a
   long rest. Needs Apply to read text items / playing techniques (how the user enters
   "stacc., brillante" in Dorico decides which).
2. **Short articulations have a time cap** (implemented: `[articulation]` in defaults.toml):
   staccato ≤ 90 ms, staccatissimo ≤ 50 ms, × 0.6 in light passages, ≥ 30 ms.
3. **Accents only where printed** – the extra accents in the playback copies made every
   note of the leaping figure equally strong; with the printed notation the metric
   accents + written accents should be enough, to be judged by ear.
4. **Swells over rising figures / into peaks** (b21–22, b31–33) are the phrase rules
   already in the engine.

### HP FLUTE print vs playback copies (2026-10-31)

The user made two small projects of the solo (bars 19–40 of the cue, renumbered from bar 1;
2/4 at ♩ = 80; Flute 1/2, Flute 3 & Piccolo; SWAM Flute map = natural only, staccato 38 %,
staccatissimo 19 %, notes 85 %): `C:\Users\kspie\Documents\Dorico Projects\HP FLUTE.dorico`
(playback: dots, staccatissimo, accents, swells and spikes written as notation; **no Play-mode
edits**) and `HP FLUTE print.dorico` (as printed). In the print copy "stacc., brillante" is
one custom text playing technique reading "staccato", linked to `pt.staccato` (encoding:
`../../finale2dorico/docs/RESEARCH.md`, last section). The user kept it generic on purpose.

Compared with `tools/compare_played.py` (played length per note in ms, Flute 1, 231 notes):

| Print copy played by | notes within 15 % of the playback copy |
|---|---|
| Dorico alone, measured from the user's MIDI export (2026-11-01): the technique shortens unmarked notes only in bars 1–2, until the first slur; 85 % (80 ms instead of 36) after that | 111 |
| Apply, technique text "staccato" | 193 |
| Apply, technique text "stacc., brillante" (simulated in a scratch copy) | 221 |

What the playback copy showed, and the rules taken from it (all in the code now):
1. **Slur ends stay long under "stacc."**: 13 last notes of two-note 32nd slurs, running into
   the next note, are undotted (80 ms); the one slur end followed by a rest (bar 7, a 16th) is
   dotted. → `passages.effective_articulations(..., rest_after)`.
2. **Brillante = as short as the flute speaks on every value**: dotted 16ths were made
   staccatissimo (36 ms, like the 32nd runs); 8ths 71 ms only because staccatissimo was the
   shortest choice. User chose ~36–40 ms throughout → `[articulation] light_factor = 0.45`
   (16ths now 41 ms, 8ths 47 ms: Apply never goes below 1/8 of the written length).
3. **Open hairpins are local swells**: the print has three cresc. hairpins with no end dynamic
   (bars 2, 8, 17) and mf again only at bar 18; read literally (+2 levels, stays) the attack
   velocity climbed 95 → 124. The playback copy writes a return to mf/mp after every swell.
   User chose "local swell, then back" → `[dynamics] open_hairpin = "swell"`
   (`engine.open_hairpin_returns`): back to the earlier level by the next phrase (note after a
   rest or starting a slur, ≤ 1 bar), as shaping on top of the literal reading. Velocity now 89–104.
4. Remaining differences are the user's extra accents and dynamic spikes (bar 6: f → ffffff
   → ppp inside a beat), i.e. accent depth (needs the dynamics lane, test I).

## Next

- Repeat on more pairs when the user finds them (other score/playback copies; the
  VV1m2 drafts).
- Turn findings 1, 2, 4 and 6 into profile parameters; 3 into a rule with strength per
  style; 5 into a checklist for expression-map setup rather than Apply output.
