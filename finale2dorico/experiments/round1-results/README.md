# Round 1 results (2026-10-26)

Reported by the user, plus Dorico's application logs (`%APPDATA%\Steinberg\Dorico 5\application*.log`).

| File | Result |
|---|---|
| 01, 03-08 | Open. **No noteheads.** Dorico says "created in Dorico 3". Double-clicking a note crashes Dorico (crash dumps in `%LOCALAPPDATA%\CrashDumps\Dorico5.exe.*.dmp`). |
| 02 (seeded) | Opens, noteheads fine; says "created in an earlier version" (seed fileVersion 1.1096 = Dorico 4.0.5). |
| 07 | Dynamics/hairpins right, but not grouped. User grouped them and saved: `07-saved-by-dorico.dorico` (kept here). |
| 08 | No articulations visible (probably because no noteheads). |
| 09, 10 | Slurs visible; can't tell if they are real slurs; double-click crashed. |
| 11, 12 | Opened (log); not reported on. |

Findings:
- `fileVersion` 1.982 is wrong (my Round 0 note was mistaken). Every project the user saved in
  5.1.60 has **1.1299**. Fixed.
- Logs: no warnings while loading; minimal files got playback template `playbacktemplate.silence`,
  which is the user's default (`preferences.xml` > `defaultPlaybackTemplate`). So "write no
  playback data → user's default template" works.
- Dorico-saved 07: Dorico filled in `scoreOptions`, layout options, `playModeData`, and every
  library collection (notehead/rest/flag/glyph/composite definitions at about the size of a
  native project's). Note events were unchanged.
- Dynamic groups (user's edit): one `DynamicGroupEventDefinition` (duration 0) at the group start;
  its element's `subElements` hold every dynamic (`ImmediateChange…`) and hairpin
  (`GradualChange…`, with `duration`) with `position` relative to the group start and
  `scoreSubElementID` 0, 1, 2… Grouped chains: dynamic → hairpin → dynamic at its end;
  hairpin → hairpin back to back.
