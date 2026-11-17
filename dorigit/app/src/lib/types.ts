// Mirrors the serde output of dorigit-core / dorico-format (see app/src-tauri/src/main.rs).

export type PlaybackMode = "milestones" | "always" | "never";

export interface Settings {
  store_dir: string;
  watch_dirs: string[];
  restore_dir: string | null;
  ignore: string[];
  playback: { mode: PlaybackMode; keep_if_under_bytes: number };
  auto_snapshot: boolean;
  settle_ms: number;
}

export interface Status {
  settings: Settings;
  settings_path: string;
  watching: string[];
  watch_errors: string[];
  version: string;
}

export interface Family {
  id: string;
  display_name: string;
  title: string;
  files: Record<string, string>;
  pending_forks: Record<string, string>;
  last_snapshot: number | null;
  snapshot_count: number;
  size: number;
}

export type PlaybackReason =
  | "milestone"
  | "first_in_history"
  | "setup_changed"
  | "small"
  | "policy_always"
  | "unchanged"
  | "skipped"
  | "not_present";

export interface Snapshot {
  family: string;
  id: string;
  short_id: string;
  parents: string[];
  time: number;
  branches: string[];
  file_name: string;
  path: string;
  kind: "auto" | "manual" | "import";
  milestones: { name: string; message: string }[];
  summary: { text: string; music_changes: number; setting_changes: number; parent: string | null };
  playback_stored: boolean;
  playback_reason: PlaybackReason;
  playback_borrow_from: string | null;
  playback_setup_changes: string[];
  has_thumb: boolean;
  dorico_version: string;
  title: string;
}

export type SnapshotOutcome =
  | { outcome: "created"; snapshot: Snapshot }
  | { outcome: "unchanged"; family: string; id: string };

export type Activity =
  | { type: "snapshot"; path: string; outcome: SnapshotOutcome }
  | { type: "error"; path: string; message: string };

export type Change = "added" | "removed" | "modified";

export interface EventChange {
  change: Change;
  owner: string;
  lane: string;
  kind: string;
  where: string;
  bar: number | null;
  position: string;
  text: string;
  details: string[];
  props: string[];
}

export interface FlowDiff {
  flow_id: string;
  name: string;
  old_name: string | null;
  change: Change;
  meters: [string[], string[]] | null;
  /** Attached picture before -> after ("none" when absent); omitted when unchanged. */
  video?: [string, string];
  owners: { owner: string; changes: EventChange[] }[];
  total: number;
}

export type SettingChange =
  | { type: "value"; path: string; old: string | null; new: string | null }
  | { type: "item_added"; path: string; name: string }
  | { type: "item_removed"; path: string; name: string };

export interface ScoreDiff {
  old_title: string;
  new_title: string;
  old_saved: number | null;
  new_saved: number | null;
  info: { key: string; old: string; new: string }[];
  players: { change: Change; old: string | null; new: string | null }[];
  flows: FlowDiff[];
  options: SettingChange[];
  layouts: SettingChange[];
}

export interface RestoreOutcome {
  path: string;
  playback_from: string | null;
  omitted: string[];
}

export interface ImportItem {
  path: string;
  outcome: SnapshotOutcome | null;
  error: string | null;
}

/** Bars a variant is meant to be about ("17"-"32", optionally in one flow). */
export interface BarRange {
  flow?: string | null;
  from: string;
  to: string;
}

export interface Variant {
  branch: string;
  name: string;
  file_name: string;
  base_branch: string;
  base_snapshot: string;
  bars?: BarRange | null;
  notes: string;
  tags: string[];
  created: number;
}

export interface DiffRange {
  from: string;
  to: string;
  changes: number;
  players: string[];
}

export interface VariantStatus {
  variant: Variant;
  tip: string | null;
  path: string | null;
  fork_point: string | null;
  main_tip: string | null;
  differs: { flow: string; ranges: DiffRange[] }[];
  music_changes: number;
  main_changes_since: number;
  outside_range: string[];
}

/** Before/after notation (MEI) of one flow's changed bars. */
export interface DiffNotation {
  flow_id: string;
  before: string | null;
  after: string | null;
  before_bars: [string, string] | null;
  after_bars: [string, string] | null;
  players: string[];
  truncated: boolean;
}

/** Merge preview (dorigit-core merge.rs). */
export type MergeOutcome = "conflict" | "review" | "auto" | "same";
export type MergeLane = "structure" | "music" | "orchestration" | "engraving" | "settings" | "playback";

export interface MergeItem {
  outcome: MergeOutcome;
  lane: MergeLane;
  side: "ours" | "theirs" | "both";
  flow: string;
  owner: string;
  voice: string;
  bar: string;
  ours: string[];
  theirs: string[];
  reason: string;
}

export interface MergePreview {
  items: MergeItem[];
  structure: { flow: string; side: "ours" | "theirs" | "both"; text: string }[];
  counts: { conflict: number; review: number; auto: number; same: number };
  integrity: string[];
}
