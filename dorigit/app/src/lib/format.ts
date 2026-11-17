import type { PlaybackReason, Snapshot } from "./types";

export function when(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeOnly(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function dayLabel(ts: number): string {
  const d = new Date(ts * 1000);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86_400_000);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "Today";
  if (same(d, yesterday)) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "long", year: "numeric" });
}

export function relative(ts: number | null): string {
  if (!ts) return "never";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.round(s / 86400)} days ago`;
  return when(ts);
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function stem(fileName: string): string {
  return fileName.replace(/\.dorico$/i, "");
}

const REASONS: Record<PlaybackReason, string> = {
  milestone: "kept for this milestone",
  first_in_history: "kept (first version)",
  setup_changed: "kept: plugin setup changed",
  small: "kept (small)",
  policy_always: "kept (always keep)",
  unchanged: "kept (identical to an earlier copy)",
  skipped: "not kept",
  not_present: "none in this file",
};

export function playbackLabel(s: Snapshot): string {
  const r = REASONS[s.playback_reason] ?? s.playback_reason;
  return r.charAt(0).toUpperCase() + r.slice(1);
}

/** Stable colour per file name, for the file chips and timeline dots. */
export function fileColor(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return `hsl(${h % 360} 55% 55%)`;
}

/** "kArticulationDuration=kStaccatoTenuto" -> "Articulation duration: staccato tenuto" (best effort). */
export function prettyProp(p: string): string {
  const [k, v = ""] = p.split("=");
  const words = (s: string) =>
    s
      .replace(/^k(?=[A-Z])/, "")
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .toLowerCase();
  const key = words(k);
  return v ? `${key[0]?.toUpperCase()}${key.slice(1)}: ${words(v)}` : key;
}

/** Make detail strings like "removed ArticulationDuration=kStaccatoTenuto" readable. */
export function prettyDetail(d: string): string {
  return d
    .replace(/([A-Za-z_]+)=([^;,]+)/g, (_m, k: string, v: string) => prettyProp(`${k}=${v}`))
    .replaceAll(" -> ", " → ");
}
