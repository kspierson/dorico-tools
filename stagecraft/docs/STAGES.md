# Stage files

A **stage file** (TOML) is stagecraft's placement setup: the space (microphones and the rules
every player follows), an air EQ and the players' seats. Everything VSS2 kept fixed or hidden is
a number here. `src/stage.rs` turns a stage into per-player **taps** (one delayed, scaled copy
per microphone and output) plus an EQ, or renders them as impulse responses.

```sh
B=./target/release/stagecraft
P="…/Harry Potter Cues Plus 5 + LASS3.dorico"
$B stage from-project "$P" --out hp5.toml                 # VSS2-compatible
$B stage from-project "$P" --space stagecraft/stages/film-stage-starter.toml --out hp5-film.toml
                                           # same seating, stagecraft's own space
$B serve hp5-film.toml                     # the editor: http://localhost:8417/ (Windows browser too)
$B stage render hp5.toml --out hp5/        # per player: ir-true-stereo.wav + taps.json
$B stage check                             # VSS2-compatible model vs every captured setting
```

**The editor** (`stagecraft serve STAGE`, `src/serve.rs` + `editor/index.html`): the stage
from above (microphones at the bottom); drag players and microphones; every setting in the
side panel; the selected player's copies (delay, level, path) in a table and as lines to each
microphone; **Save** writes the stage file. **Audition**: load dry stems (WAV) in the browser,
each matched to a player by name, and hear them through the current stage while you change it
(direct sound + first reflections; the shared reflection layer is your reverb and isn't played
here yet). The page is a thin front end over JSON calls (`/api/stage`, `/api/save`,
`/api/ir/N`) that become commands of the Playback app (PLANNED_WORK §2.11) later.
`#player=N` / `#mic=N` in the address opens with that selection.

Stage files made from the user's projects belong in `stagecraft/captures/stages/` (git-ignored).

## How a player is placed

For every **emitter** of the player (a point; or a section's two ends, the left input at the
left end and the right input at the right end), for the emitter itself and its **image** in each
room surface (first reflections), for every microphone `m` and each output it feeds:

- **distance** d = |source − microphone|
- **delay** = d / `speed_of_sound`, minus a shift: the player's nearest microphone
  (`depth_delay` = 0, VSS2) or `depth_reference_m` (`depth_delay` = 1: real arrival times)
- **gain dB** = `level_db` + player `gain_db` − 20 · `distance_exponent` · log10(d)
  + 20 · log10(pattern) + the microphone's `left_db` / `right_db` + the surface's reflection
  dB (reflections), where pattern = (1 − `pattern`) + `pattern` · cos(angle between the mic's
  `direction` and the source); plus the mic's own `delay_ms`
- then the EQs, linear phase: the player's VSS2 **air** (`amount(air)` × `shape(f)`), its
  **brightness** (same shape, `brightness_db` at 16 kHz) and, if on, **air absorption** by
  path length (ISO 9613-1 for the space's temperature and humidity).

Each output is the sum of its copies. A point is fed by both inputs at half level (VSS2 sums
its inputs); a section's ends each by one input.

## Settings

### `[space]`

| Setting | Meaning | VSS2 (measured) | Changing it |
|---|---|---|---|
| `speed_of_sound` | m/s | 343 | timing scale (temperature: ≈ 331 + 0.6 · °C) |
| `distance_exponent` | level ∝ 1/d^exponent | 1.0 (ScSB, Stdi), 0.88 (ScSA) | lower = back rows less quiet (closer-sounding); 1.0 is physical for the direct sound |
| `level_db` | overall level | room base + GOLv: ScSA 16.5, ScSB 19.3, Stdi 19.0 (+ room level) | gain staging only |
| `depth_delay` | 0 = every player's nearest mic arrives at the same moment; 1 = real arrival times | 0 | **depth by timing**: the back of the orchestra arrives later than the front (≈ 2.9 ms per metre), as on a real recording; 0 keeps everyone tight |
| `depth_reference_m` | the distance that arrives with no delay when `depth_delay` > 0 | — | set to the nearest player's distance so nobody is cut |
| `exact_delays` | fractional-sample delays | false (VSS2 rounds each mic's travel time to whole samples) | true = exact timing (stagecraft's default for new stages) |
| `air_absorption` | physical treble loss by path length | false (VSS2's Air is a fixed EQ per player) | far players and reflections get darker, as in a hall; at 20 °C / 50 %: ≈ 0.1 dB/m at 8 kHz |
| `temperature_c`, `humidity_pct` | for the absorption | — | dry air absorbs more treble |
| `[space.room]` | a shoebox: `width_m`, `length_m`, `height_m`, `front_m` (y of the front wall) and a reflection level per surface (`floor_db`, `ceiling_db`, `left_db`, `right_db`, `front_db`, `back_db`; absent = no reflection) | none | every player gets one first reflection per surface at every mic: floor and wall cues for height, depth and width |
| `[space.reflections]` | per-player send into the shared early-reflection layer: `send_db` + `per_m_db` × (distance to the main mics − `reference_m`) | none (the user's sends were set by hand) | front drier, back wetter, computed from position |

### `[[space.mics]]` (any number)

| Setting | Meaning | VSS2 |
|---|---|---|
| `name` | label | L, C, R |
| `position` | x across (− left), y back from the stage edge (− in front), z up; metres | Decca tree: L/R at ±1 m, C 1.2 m forward; ScSA keeps it ≤ 3 m in front and ≤ 8 m high, ScSB ≤ 3.5 m in front |
| `direction` | where it points | L/R turned ±45°, C forward |
| `pattern` | 0 omni, 0.5 cardioid, 1 figure 8 | omni (tree), cardioid (studio pair) |
| `left_db`, `right_db` | mix level into each output (absent = not routed) | L 0 / –, C −9 / −9, R – / 0 |
| `delay_ms` | extra delay (time-aligning a spot mic) | 0 |

VSS2 had exactly one main array. Here **any microphone plan** works: outriggers, section spot
mics, ambient pairs, each with its own mix level, which is how mic bleed (PLANNED_WORK §7.12)
comes out of the same rules.

### `[air]`

`amount(air)` × `shape(f)` dB: `shape_hz`/`shape_db` (dB per unit; ∝ f² above the last point),
`amount_air`/`amount` (interpolated), `no_air_amount`. The VSS2 values fit every Air setting
within 0.25 dB (`stages/vss2-compat.toml`).

### `[[players]]`

| Setting | Meaning |
|---|---|
| `name` | label |
| `position` | x, y, z (m); VSS2 sources sit at z 1.5 |
| `gain_db` | player level (VSS2's PiOG + direct level) |
| `air` | VSS2-scale air value (−100 … 100); negative = brighter. `--space` turns it into `brightness_db` (the same curve) |
| `brightness_db` | presence: dB at 16 kHz on the air curve, independent of distance (the flutes' VSS2 Air −100 = +17.5 dB) |
| `facing_deg` | 0 = toward the microphones; turns a section's line |
| `width_m` | a section: left input at the left end, right input at the right end (0 = a point). VSS2's own sections don't match this yet (open) |
| `note` | free text (where it came from; sections are flagged) |

## How close the VSS2-compatible stage is (2026-11-02)

`stage check` on all 512 captured settings it covers (point sources in rooms with a saved mic
setup; no GoLR/DoLR offsets; not muted), direct sound from 4 ms before the first copy to 4 ms
after the last, 200 Hz–20 kHz:

| Room | Settings | Residual median (dB) | Level at 1 kHz, median (dB) |
|---|---|---|---|
| ScSA (Harry Potter, +1.5 / −1.5) | 91 / 43 | −28 / −33 | 0.09 |
| ScSB tree 3.0 / 3.5 m in front | 25 / 84+78 | −27 / −30 | 0.16 |
| ScSB tree at the stage edge (Christmas) | 94 | −22 | 0.15 |
| Stdi (cardioid pair) | 94 | −19 | 0.40 |
| ScSB coincident pair (HP - birds) | 3 | −13 | 0.43 |

−30 dB means about 3 % of the energy differs. Outliers (up to +3 dB, i.e. no match): piano,
some percussion (bass drum, tambourine), whose VSS2 settings carry something the model
doesn't (yet). Not modelled: sections (2 emitters), GoLR/DoLR input balance, the reflections
(captured IRs or a shared layer supply those).

Found while building it: VSS2 rounds **each microphone's travel time to whole samples** and
subtracts the earliest, so copies sit on whole samples (a 1-sample difference was the largest
error before this was modelled).

## The film-stage starter (`stages/film-stage-starter.toml`)

stagecraft's own space for trying the new parts: Decca tree above the conductor, outriggers,
woodwind/horn/brass spot mics (mixed low, so they mostly add bleed and definition), a 26 × 32 ×
12 m room with first reflections, real arrival times, physical air absorption and reflection
sends. Starting values from typical scoring-stage practice, **not measured**: to be tuned by ear
and against the user's reference recordings (E5/E7). `--space` keeps a project's seating and
turns each VSS2 Air value into the same brightness curve, so tone stays put and the space's air
absorption adds the distance part on top.
