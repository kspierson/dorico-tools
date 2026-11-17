// Calls into the Rust backend. Outside Tauri (plain `npm run dev` in a browser)
// a small mock is used so the UI can be worked on without the desktop shell.

import type {
  Activity,
  BarRange,
  DiffNotation,
  Family,
  ImportItem,
  MergePreview,
  RestoreOutcome,
  ScoreDiff,
  Settings,
  Snapshot,
  SnapshotOutcome,
  Status,
  Variant,
  VariantStatus,
} from "./types";
import * as mock from "./mock";

export const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

async function call<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (!inTauri) return mock.call<T>(cmd, args);
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(cmd, args);
}

export const api = {
  status: () => call<Status>("status"),
  saveSettings: (settings: Settings) => call<Status>("save_settings", { settings }),
  families: () => call<Family[]>("families"),
  snapshots: (family: string) => call<Snapshot[]>("snapshots", { family }),
  diff: (family: string, newId: string, oldId?: string | null) =>
    call<ScoreDiff>("diff", { family, new: newId, old: oldId ?? null }),
  thumbnail: (family: string, id: string) => call<ArrayBuffer>("thumbnail", { family, id }),
  restore: (family: string, id: string, open: boolean) => call<RestoreOutcome>("restore", { family, id, open }),
  snapshotNow: (path: string, milestone?: string | null) =>
    call<SnapshotOutcome>("snapshot_now", { path, milestone: milestone ?? null }),
  addMilestone: (family: string, id: string, name: string) => call<void>("add_milestone", { family, id, name }),
  removeMilestone: (family: string, id: string, name: string) => call<void>("remove_milestone", { family, id, name }),
  importFiles: (paths: string[]) => call<ImportItem[]>("import_files", { paths }),
  notationDiff: (family: string, newId: string, oldId: string | null, flowId: string) =>
    call<DiffNotation>("notation_diff", { family, new: newId, old: oldId, flowId }),
  mergePreview: (family: string, ours: string, theirs: string, base?: string | null) =>
    call<MergePreview>("merge_preview", { family, ours, theirs, base: base ?? null }),
  variantBoard: (family: string) => call<VariantStatus[]>("variant_board", { family }),
  newVariant: (path: string, name: string, bars: BarRange | null) =>
    call<{ path: string; variant: Variant }>("new_variant", { path, name, bars }),
  updateVariant: (
    family: string,
    branch: string,
    change: { name?: string; notes?: string; tags?: string[]; bars?: BarRange; clearBars?: boolean },
  ) =>
    call<Variant>("update_variant", {
      family,
      branch,
      name: change.name ?? null,
      notes: change.notes ?? null,
      tags: change.tags ?? null,
      bars: change.bars ?? null,
      clearBars: change.clearBars ?? null,
    }),
  openPath: (path: string) => call<void>("open_path", { path }),
  reveal: (path: string) => call<void>("reveal", { path }),
};

/** Subscribe to watcher activity (snapshots taken on save). Returns an unsubscribe function. */
export async function onActivity(handler: (a: Activity) => void): Promise<() => void> {
  if (!inTauri) return () => {};
  const { listen } = await import("@tauri-apps/api/event");
  return listen<Activity>("activity", (e) => handler(e.payload));
}

export async function pickDoricoFiles(): Promise<string[]> {
  if (!inTauri) return [];
  const { open } = await import("@tauri-apps/plugin-dialog");
  const r = await open({ multiple: true, filters: [{ name: "Dorico projects", extensions: ["dorico"] }] });
  return r === null ? [] : Array.isArray(r) ? r : [r];
}

export async function pickFolder(title: string): Promise<string | null> {
  if (!inTauri) return null;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const r = await open({ directory: true, multiple: false, title });
  return typeof r === "string" ? r : null;
}

const thumbCache = new Map<string, Promise<string | null>>();

/** Object URL for a snapshot thumbnail (cached), or null. */
export function thumbnailUrl(s: Snapshot): Promise<string | null> {
  if (!s.has_thumb) return Promise.resolve(null);
  let p = thumbCache.get(s.id);
  if (!p) {
    p = api
      .thumbnail(s.family, s.id)
      .then((buf) => (buf.byteLength ? URL.createObjectURL(new Blob([buf], { type: "image/png" })) : null))
      .catch(() => null);
    thumbCache.set(s.id, p);
  }
  return p;
}
