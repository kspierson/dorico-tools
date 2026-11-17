# Kontakt libraries: measurements (Project C)

Round 1 rendered 2026-11-02 by the user in Cubase 13 from the generated track archives
(`HPCaptures\kontakt\`, `vi_measure.py kit`); WAVs in `D:\renders` (23 GB, too big for C:).
Analysis: `uv run --with numpy python dorico-hp/tools/vi_measure.py analyse /mnt/d/renders`
→ `research/vi/measurements/<proj>-sNN.json` (plans: `.plan.json`). Levels are dBFS of the
plug-in output with the saved Kontakt volumes, 48 kHz.

## What rendered

| Source | Sounds | Silent |
|---|---|---|
| Template (Kontakt 7) | IW slots 1, 2, 4, 5, 6, 21, 24; IB slots 3, 7, 8, 9, 10 — every channel | slots 11, 14, 16–20, 22, 23: **empty instances** (state 4 kB, nothing loaded; Default maps) |
| HP (Kontakt 6.4 states → Kontakt 7) | harps (8, 30), celeste (7), LASS **Violin I only** (slot 9 ch 1) | LASS ch 3/5/7/9; SM brass (13, 26, 27, 28); mallets (6, 29, 42); tubular bells (44); choir/treble (16, 20); slot 34 Joshua Bell is **empty** (state 2 kB) |

Cause (user, 2026-11-16): in the HP project each Kontakt instance sends its players to separate
**outputs** (Trumpet 1 → st.1, Trumpet 2 → st.2, …); a Cubase instrument track only carries output
1, so only players on st.1 were captured (LASS Violin I, harps, celeste). The port list in
enginedata's mixer XML doesn't show this (every slot lists the default "st. 1 + aux 1–4": on this
PC Kontakt 6.2.1 can't load the 6.4 states, so Dorico saved the defaults). Round 1b: the user
activates all Kontakt outputs on those tracks and exports every output channel
(`HPCaptures\kontakt\README-outputs.txt`); `vi_measure.py analyse` picks, per player, the WAV
of that track (`HP sNN` in the name, any folder) where the player's segment has sound.

## Template IW / IB (all channels)

Table from the A/B/C batteries: "range" = probed notes that sound at the right pitch (probe
covered the written range ± 3); "dyn range" = level at CC 127 − CC 16 at the middle register;
"top" = median level at CC 127; "short" = shortest note within 3 dB of a 1 s note's peak (vel 115);
"onset" = median onset at velocity 100 (CC 90).

| Channel | range | dyn range dB | top dBFS | at 64 | short ms | onset ms |
|---|---|---|---|---|---|---|
| Flute 1 / 2 / 3 (CC11) | 60–96 | 40 / 39 / 37 | −32 / −31 / −34 | −49 / −50 / −51 | 120 | 45 |
| Piccolo | 72–105 | 39 | −31 | −51 | 300 | 32 |
| Oboe 1 / 2 / 3 | 58–93 | 39 / 39 / 41 | −36 / −35 / −32 | −49 / −50 / −53 | 40 | 35 |
| English Horn | 52–84 | 39 | −34 | −53 | 300 | 30 |
| Clarinet 1 / 2 / 3 | 50–92 | 39 / 39 / 40 | **−30 / −36 / −39** | −50 / −56 / −57 | 80 | 40 |
| Eb Clarinet | 55–96 | 39 | **−44** | −58 | 80 | 30 |
| Bass Clarinet / Contrabass Cl. | 34–75 / 22–61 | 38 / 39 | −40 / −37 | −60 / −54 | 50 / 60 | 30 / 50 |
| Bassoon 1 / 2 / 3, Contrabassoon | 34–78 / 22–56 | 39–40 | −31 / −31 / −33 / −33 | −48…−53 | 20–80 | 30–60 |
| Soprano / Alto / Tenor / Bari Sax (×2 each) | 56–88 / 49–81 / 44–76 / 36–69 | 39 | −29…−32 | −45…−50 | 20–100 | 35–72 |
| Alto Flute / Bass Flute | 55–91 / 48–84 | 39 | −39 / −34 | −52 / −48 | 80 / 150 | 42 / 72 |
| Horn 1–6 (IB, CC1) | 33–79 | 24–26 | −20…−23 | −32…−38 | 80 | 25 |
| Trumpet 1–4 | 52–85 | 27–29 | −18…−20 | −31…−35 | 30 | 15 |
| Trombone 1–3, Bass Trombone | 37–75 / 31–70 | 26–34 / 23 | −21…−22 / −20 | −33…−39 | 40–60 | 28 |
| Tuba / Euphonium 1–2 | 25–61 / 37–73 | 22 | −21 / −15 | −31 / −25 | 80 | 28–40 |

Findings:
1. **IW's CC11 range is about 39 dB (16 → 127), IB's CC1 range about 22–29 dB.** Under the
   same Dorico dynamic curve, IW woodwinds swing much wider than IB brass; at CC 127 IB brass is
   10–15 dB louder than IW (−20 vs −32 dBFS), euphonium louder again (−15).
2. **Clarinet balance:** Clarinet 2 and 3 are 6–9 dB quieter than Clarinet 1 at the same CC, Eb
   clarinet 14 dB. Same map, so it's the Kontakt instrument volumes in the template state (or
   different patches) — ask whether intended.
3. **Short notes:** most need 40–120 ms to reach full level (trumpet 30 ms); piccolo, English
   horn 300 ms, bass flute 150 ms. Shorter notes at vel 70 are 10–24 dB quieter.
4. **Attack:** onsets 15–72 ms; low velocities (≤ 30) are much slower (100–300 ms) on IW.
5. **Legato:** the gap test's dip measure is noisy (the dip doesn't grow steadily with the gap);
   roughly, IW/IB keep notes connected for gaps up to ~15–40 ms, trombones ~80 ms. Needs a better
   transition detector before using it for map lengths.

## HP (what sounded)

| Channel | range | dyn range dB | top dBFS | at 64 | short ms | onset ms |
|---|---|---|---|---|---|---|
| LASS Violin I (CC1) | 55–99 | 18 | −23 | −36 | 200 | 15 |
| Spitfire Harp 1 / 2 (velocity) | 25–104 | 38 | −38 | −50 | – | – |
| Celeste (velocity) | 57–105 | 14 | −38 | −45 | – | – |

LASS Violin I: CC1 range only 18 dB; notes need ~200 ms to reach level.
