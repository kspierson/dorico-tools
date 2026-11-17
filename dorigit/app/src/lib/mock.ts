// Browser-only stand-in for the Rust backend, so `npm run dev` shows a working UI.
// Data shapes match types.ts; contents are illustrative.

import type { DiffNotation, Family, MergePreview, ScoreDiff, Settings, Snapshot, Status, VariantStatus } from "./types";

const settings: Settings = {
  store_dir: "C:\\Users\\you\\AppData\\Local\\dorigit\\store",
  watch_dirs: ["C:\\Users\\you\\Documents\\Dorico Projects"],
  restore_dir: null,
  ignore: ["Backup Projects", "AutoSave"],
  playback: { mode: "milestones", keep_if_under_bytes: 2 * 1024 * 1024 },
  auto_snapshot: true,
  settle_ms: 2000,
};

const fam = "c1609642780";
const base = 1618714367;
const snap = (i: number, over: Partial<Snapshot>): Snapshot => ({
  family: fam,
  id: `${i}`.padStart(40, "a"),
  short_id: `${i}`.padStart(7, "a"),
  parents: i > 1 ? [`${i - 1}`.padStart(40, "a")] : [],
  time: base + i * 5400,
  branches: [],
  file_name: "Harry Potter Cues Plus 5.dorico",
  path: "C:\\Users\\you\\Documents\\Dorico Projects\\Harry Potter Cues Plus 5.dorico",
  kind: "auto",
  milestones: [],
  summary: { text: "3 changes in 2 parts", music_changes: 3, setting_changes: 0, parent: null },
  playback_stored: false,
  playback_reason: "skipped",
  playback_borrow_from: "1".padStart(40, "a"),
  playback_setup_changes: [],
  has_thumb: false,
  dorico_version: "3.5.12",
  title: "Untitled Project 1",
  ...over,
});

const snapshots: Snapshot[] = [
  // a burst: three quick saves of the same file after the newest version
  snap(8, { time: base + 5 * 5400 + 9 * 60, summary: { text: "2 changes in 1 part", music_changes: 2, setting_changes: 0, parent: null } }),
  snap(7, { time: base + 5 * 5400 + 5 * 60, summary: { text: "1 change in 1 part", music_changes: 1, setting_changes: 0, parent: null } }),
  snap(6, { time: base + 5 * 5400 + 2 * 60, summary: { text: "4 changes in 2 parts", music_changes: 4, setting_changes: 0, parent: null } }),
  snap(5, { summary: { text: "25 changes in 21 parts; 2 settings", music_changes: 25, setting_changes: 2, parent: null }, branches: ["harry-potter-cues-plus-5-1a2b3c"] }),
  snap(4, { file_name: "Harry Potter Cues Plus 5 (SILENT).dorico", playback_stored: true, playback_reason: "setup_changed", playback_borrow_from: null, playback_setup_changes: ["-18 Kontakt", "-4 Pianoteq 6 STAGE"], summary: { text: "no musical changes", music_changes: 0, setting_changes: 0, parent: null }, branches: ["harry-potter-cues-plus-5-silent-9f8e7d"] }),
  snap(3, { milestones: [{ name: "Sent to orchestrator", message: "Sent to orchestrator" }], playback_stored: true, playback_reason: "milestone", playback_borrow_from: null }),
  snap(2, { summary: { text: "74 changes in 18 parts", music_changes: 74, setting_changes: 0, parent: null } }),
  snap(1, { summary: { text: "first snapshot", music_changes: 0, setting_changes: 0, parent: null }, playback_stored: true, playback_reason: "first_in_history", playback_borrow_from: null, kind: "import" }),
];

const families: Family[] = [
  { id: fam, display_name: "Harry Potter Cues Plus 5", title: "Untitled Project 1", files: { a: "x", b: "y" }, pending_forks: {}, last_snapshot: snapshots[0].time, snapshot_count: 5, size: 187_000_000 },
  { id: "c1653848970", display_name: "Obi-Wan - End Credits", title: "Obi-Wan", files: { a: "x" }, pending_forks: {}, last_snapshot: base - 90000000, snapshot_count: 6, size: 64_000_000 },
];

const diff: ScoreDiff = {
  old_title: "Untitled Project 1",
  new_title: "Untitled Project 1",
  old_saved: base,
  new_saved: base + 54000,
  info: [],
  players: [{ change: "modified", old: "Trombone 3", new: "Bass Trombone" }],
  flows: [
    {
      flow_id: "2",
      name: "Quidditch 2004",
      old_name: null,
      change: "modified",
      meters: null,
      total: 4,
      owners: [
        { owner: "Flute 1", changes: [{ change: "modified", owner: "Flute 1", lane: "", kind: "dynamic", where: "bar 19 beat 1", bar: 19, position: "72", text: "", details: ["ff -> fff"], props: [] }] },
        {
          owner: "Trumpet (B Flat) 1",
          changes: [
            { change: "modified", owner: "Trumpet (B Flat) 1", lane: "voice 1", kind: "note", where: "bar 16 beat 3", bar: 16, position: "62", text: "B5 quaver", details: ["removed ArticulationDuration=kStaccatoTenuto"], props: [] },
            { change: "added", owner: "Trumpet (B Flat) 1", lane: "voice 1", kind: "note", where: "bar 18 beat 1", bar: 18, position: "68", text: "D6 crotchet", details: [], props: ["ArticulationForce=kMarcato"] },
            { change: "removed", owner: "Trumpet (B Flat) 1", lane: "voice 1", kind: "note", where: "bar 18 beat 2", bar: 18, position: "69", text: "C6 crotchet", details: [], props: [] },
          ],
        },
      ],
    },
  ],
  options: [{ type: "value", path: "engravingOptions/fingeringEngravingOptions/verticalGapBetweenCoincidentFingerings", old: "1/4", new: "1/8" }],
  layouts: [{ type: "item_added", path: "array/layout[layoutID=39]", name: "Tuba" }],
};

const variantBoard: VariantStatus[] = [
  {
    variant: {
      branch: "harry-potter-cues-plus-5-horns",
      name: "horns",
      file_name: "Harry Potter Cues Plus 5 [horns].dorico",
      base_branch: "harry-potter-cues-plus-5",
      base_snapshot: "5".padStart(40, "a"),
      bars: { from: "17", to: "32" },
      notes: "Horns take the tune at 17; brighter. Play for director Thursday.",
      tags: ["director prefers"],
      created: base + 6 * 5400,
    },
    tip: "6".padStart(40, "b"),
    path: "C:\\Users\\you\\Documents\\Dorico Projects\\Harry Potter Cues Plus 5 [horns].dorico",
    fork_point: "5".padStart(40, "a"),
    main_tip: "8".padStart(40, "a"),
    differs: [
      {
        flow: "Quidditch 2004",
        ranges: [
          { from: "17", to: "24", changes: 38, players: ["Horn (F) 1", "Horn (F) 2", "Violin I"] },
          { from: "29", to: "32", changes: 12, players: ["Horn (F) 1", "Horn (F) 3"] },
          { from: "40", to: "40", changes: 2, players: ["Trumpet (B Flat) 1"] },
        ],
      },
    ],
    music_changes: 52,
    main_changes_since: 3,
    outside_range: ["Quidditch 2004 b.40"],
  },
  {
    variant: {
      branch: "harry-potter-cues-plus-5-strings-only",
      name: "strings only",
      file_name: "Harry Potter Cues Plus 5 [strings only].dorico",
      base_branch: "harry-potter-cues-plus-5",
      base_snapshot: "5".padStart(40, "a"),
      bars: null,
      notes: "",
      tags: ["too thin?"],
      created: base + 7 * 5400,
    },
    tip: "7".padStart(40, "b"),
    path: "C:\\Users\\you\\Documents\\Dorico Projects\\Harry Potter Cues Plus 5 [strings only].dorico",
    fork_point: "5".padStart(40, "a"),
    main_tip: "8".padStart(40, "a"),
    differs: [{ flow: "Quidditch 2004", ranges: [{ from: "17", to: "32", changes: 61, players: ["Flute 1", "Oboe 1", "Horn (F) 1", "Violin I", "Viola"] }] }],
    music_changes: 61,
    main_changes_since: 3,
    outside_range: [],
  },
];

// A made-up two-bar phrase (not from any real score), before and after one edit.
function mockMei(after: boolean): string {
  const g = after ? ' color="#3b5bdb"' : ' color="#3b5bdb"';
  const added = after ? '<note pname="d" oct="6" dur="4" color="#2f9e44"/>' : '<note pname="c" oct="6" dur="4" color="#c92a2a"/>';
  return `<?xml version="1.0" encoding="UTF-8"?><mei xmlns="http://www.music-encoding.org/ns/mei" meiversion="5.0"><meiHead><fileDesc><titleStmt><title>mock</title></titleStmt><pubStmt/></fileDesc></meiHead><music><body><mdiv><score><scoreDef key.sig="1s" meter.count="3" meter.unit="8"><staffGrp><staffDef n="1" lines="5" clef.shape="G" clef.line="2"><label>Flute 1</label></staffDef><staffDef n="2" lines="5" clef.shape="G" clef.line="2"><label>Trumpet (B♭) 1</label></staffDef></staffGrp></scoreDef><section><measure n="18"><staff n="1"><layer n="1"><beam><note pname="g" oct="5" dur="8"/><note pname="a" oct="5" dur="8"/><note pname="b" oct="5" dur="8"/></beam></layer></staff><staff n="2"><layer n="1"><note pname="b" oct="5" dur="8"${g}/><rest dur="8"/><note pname="g" oct="5" dur="8"/></layer></staff><dynam staff="1" tstamp="1">${after ? "fff" : "ff"}</dynam></measure><measure n="19"><staff n="1"><layer n="1"><note pname="c" oct="6" dur="4" dots="1"/></layer></staff><staff n="2"><layer n="1">${added}<rest dur="8"/></layer></staff></measure></section></score></mdiv></body></music></mei>`;
}

const notationDiff: DiffNotation = {
  flow_id: "2",
  before: mockMei(false),
  after: mockMei(true),
  before_bars: ["18", "19"],
  after_bars: ["18", "19"],
  players: ["Flute 1", "Trumpet (B Flat) 1"],
  truncated: false,
};

const mergePreview: MergePreview = {
  counts: { conflict: 1, review: 2, auto: 3, same: 4 },
  structure: [],
  integrity: [],
  items: [
    { outcome: "conflict", lane: "music", side: "both", flow: "Quidditch 2004", owner: "Bassoon 1", voice: "", bar: "21", ours: ["b.21 beat 1: added dynamic mf"], theirs: ["b.21 beat 1: added dynamic mp"], reason: "both versions changed this bar differently" },
    { outcome: "review", lane: "music", side: "ours", flow: "Quidditch 2004", owner: "Violin I", voice: "voice 1", bar: "17", ours: ["b.17 beat 1: note G4 crotchet -> A4 crotchet"], theirs: [], reason: "the other version changed another voice/stave of Violin I in this bar (e.g. divisi IA/IB): confirm they belong together" },
    { outcome: "review", lane: "music", side: "theirs", flow: "Quidditch 2004", owner: "Violin I", voice: "voice 2", bar: "17", ours: [], theirs: ["b.17 beat 1: note E4 crotchet -> D4 crotchet"], reason: "the other version changed another voice/stave of Violin I in this bar (e.g. divisi IA/IB): confirm they belong together" },
    { outcome: "auto", lane: "music", side: "theirs", flow: "Quidditch 2004", owner: "Horn (F) 1", voice: "voice 1", bar: "24", ours: [], theirs: ["b.24 beat 1: added note C5 minim"], reason: "" },
    { outcome: "auto", lane: "engraving", side: "ours", flow: "Quidditch 2004", owner: "(global)", voice: "", bar: "30", ours: ["b.30 beat 1: added break"], theirs: [], reason: "" },
    { outcome: "auto", lane: "settings", side: "ours", flow: "", owner: "engravingOptions/slurOptions/endpointOffset", voice: "", bar: "", ours: ["1/4 -> 1/2"], theirs: [], reason: "" },
    { outcome: "same", lane: "orchestration", side: "both", flow: "", owner: "Violin 1", voice: "", bar: "", ours: ["added Violin 1"], theirs: ["added Violin 1"], reason: "" },
  ],
};

export async function call<T>(cmd: string, _args?: Record<string, unknown>): Promise<T> {
  await new Promise((r) => setTimeout(r, 120));
  const status: Status = { settings, settings_path: "(mock)", watching: settings.watch_dirs, watch_errors: [], version: "mock" };
  const table: Record<string, unknown> = {
    status,
    save_settings: status,
    families,
    snapshots: (_args?.family === fam ? snapshots : snapshots.slice(0, 2)),
    diff,
    thumbnail: new ArrayBuffer(0),
    restore: { path: "C:\\...\\Harry Potter Cues Plus 5 (restored aaaaaa3).dorico", playback_from: null, omitted: [] },
    import_files: [],
    variant_board: variantBoard,
    merge_preview: mergePreview,
    notation_diff: notationDiff,
    new_variant: { path: `C:\\...\\Harry Potter Cues Plus 5 [${String(_args?.name ?? "new")}].dorico`, variant: variantBoard[0].variant },
    update_variant: variantBoard[0].variant,
  };
  if (!(cmd in table)) return undefined as T;
  return table[cmd] as T;
}
