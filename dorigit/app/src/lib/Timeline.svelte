<script lang="ts">
  import Thumb from "./Thumb.svelte";
  import { dayLabel, fileColor, stem, timeOnly } from "./format";
  import type { Snapshot } from "./types";

  let {
    snapshots,
    selectedId,
    loading,
    onselect,
  }: {
    snapshots: Snapshot[];
    selectedId: string | null;
    loading: boolean;
    onselect: (s: Snapshot) => void;
  } = $props();

  let fileFilter = $state("");
  let milestonesOnly = $state(false);

  let files = $derived([...new Set(snapshots.map((s) => s.file_name))].sort());
  let visible = $derived(
    snapshots.filter(
      (s) => (!fileFilter || s.file_name === fileFilter) && (!milestonesOnly || s.milestones.length > 0),
    ),
  );
  // Save bursts (your choice, 2026-10-30): every save is kept, but saves of the same file a few
  // minutes apart fold into one row showing the latest. Milestones are never folded.
  const BURST_SECONDS = 10 * 60;
  type Burst = { head: Snapshot; rest: Snapshot[] };

  let groups = $derived.by(() => {
    const out: { day: string; bursts: Burst[] }[] = [];
    for (const s of visible) {
      const day = dayLabel(s.time);
      if (out.at(-1)?.day !== day) out.push({ day, bursts: [] });
      const bursts = out.at(-1)!.bursts;
      const last = bursts.at(-1);
      const prev = last ? (last.rest.at(-1) ?? last.head) : null; // newest first: prev is later in time
      const joins =
        last &&
        prev &&
        !s.milestones.length &&
        !last.head.milestones.length &&
        s.file_name === last.head.file_name &&
        prev.time - s.time <= BURST_SECONDS;
      if (joins) last.rest.push(s);
      else bursts.push({ head: s, rest: [] });
    }
    return out;
  });

  let expanded = $state<Record<string, boolean>>({});

  // open the burst that holds the selected version (e.g. after keyboard navigation)
  $effect(() => {
    for (const g of groups)
      for (const b of g.bursts)
        if (b.rest.some((r) => r.id === selectedId) && !expanded[b.head.id]) expanded[b.head.id] = true;
  });

  function span(b: Burst): string {
    const first = b.rest.at(-1)!;
    const mins = Math.max(1, Math.round((b.head.time - first.time) / 60));
    return `${timeOnly(first.time)}–${timeOnly(b.head.time)}, ${mins} min`;
  }

  function onkey(e: KeyboardEvent) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const i = visible.findIndex((s) => s.id === selectedId);
    const next = visible[Math.max(0, Math.min(visible.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) {
      e.preventDefault();
      onselect(next);
      document.getElementById(`snap-${next.id}`)?.scrollIntoView({ block: "nearest" });
    }
  }
</script>

{#snippet row(s: Snapshot, inBurst: boolean)}
  <button
    id="snap-{s.id}"
    class="row"
    class:compact={inBurst}
    class:selected={s.id === selectedId}
    onclick={() => onselect(s)}
    role="option"
    aria-selected={s.id === selectedId}
  >
    <span class="rail" style:background={fileColor(s.file_name)}></span>
    {#if !inBurst}<Thumb snapshot={s} width={40} />{/if}
    <div class="body">
      <div class="top">
        <span class="time">{timeOnly(s.time)}</span>
        {#if !inBurst}
          <span class="chip" title={s.path}>
            <span class="dot" style:background={fileColor(s.file_name)}></span>{stem(s.file_name)}
          </span>
        {/if}
      </div>
      <div class="summary" class:quiet={s.summary.music_changes === 0}>{s.summary.text}</div>
      {#if s.milestones.length || s.playback_stored || s.kind === "import"}
        <div class="badges">
          {#each s.milestones as m}
            <span class="badge milestone">★ {m.name}</span>
          {/each}
          {#if s.playback_setup_changes.length}
            <span class="badge playback" title={s.playback_setup_changes.join("\n")}>♪ setup changed</span>
          {:else if s.playback_stored && s.playback_reason !== "small" && s.playback_reason !== "unchanged"}
            <span class="badge playback">♪ playback kept</span>
          {/if}
          {#if s.kind === "import"}
            <span class="badge muted">imported</span>
          {/if}
        </div>
      {/if}
    </div>
  </button>
{/snippet}

<section>
  <div class="filters">
    <select bind:value={fileFilter} title="Show versions of one file">
      <option value="">All files ({files.length})</option>
      {#each files as f}
        <option value={f}>{stem(f)}</option>
      {/each}
    </select>
    <label class="muted"><input type="checkbox" bind:checked={milestonesOnly} /> Milestones</label>
  </div>

  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="list scroll" tabindex="0" onkeydown={onkey} role="listbox" aria-label="Versions">
    {#if loading && snapshots.length === 0}
      <div class="empty muted">Loading history…</div>
    {/if}
    {#each groups as g (g.day)}
      <div class="day">{g.day}</div>
      {#each g.bursts as b (b.head.id)}
        {@render row(b.head, false)}
        {#if b.rest.length}
          <button class="fold" onclick={() => (expanded[b.head.id] = !expanded[b.head.id])} aria-expanded={!!expanded[b.head.id]}>
            {expanded[b.head.id] ? "▾" : "▸"}
            {b.rest.length} earlier save{b.rest.length === 1 ? "" : "s"} of this file
            <span class="muted">({span(b)})</span>
          </button>
          {#if expanded[b.head.id]}
            <div class="burst">
              {#each b.rest as s (s.id)}
                {@render row(s, true)}
              {/each}
            </div>
          {/if}
        {/if}
      {/each}
    {:else}
      {#if !loading}
        <div class="empty muted">No versions match.</div>
      {/if}
    {/each}
  </div>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--line);
    background: var(--bg);
  }
  .filters {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    border-bottom: 1px solid var(--line);
  }
  .filters select {
    flex: 1;
    min-width: 0;
  }
  .filters label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    white-space: nowrap;
  }
  .list {
    flex: 1;
    min-height: 0;
    padding: 4px 8px 16px;
    outline: none;
  }
  .day {
    position: sticky;
    top: 0;
    z-index: 1;
    padding: 10px 6px 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    background: var(--bg);
  }
  .row {
    position: relative;
    display: flex;
    gap: 10px;
    width: 100%;
    text-align: left;
    padding: 8px 10px 8px 14px;
    margin-bottom: 4px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  .row.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .rail {
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 3px;
    border-radius: 0 3px 3px 0;
  }
  .body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .top {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .time {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    font-size: 13px;
  }
  .summary {
    font-size: 13px;
    line-height: 1.35;
  }
  .summary.quiet {
    color: var(--muted);
  }
  .badges {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .fold {
    display: block;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    font-size: 12px;
    padding: 0 10px 6px 18px;
    margin-top: -2px;
    color: var(--text);
  }
  .fold:hover:not(:disabled) {
    color: var(--accent);
  }
  .burst {
    margin: 0 0 6px 14px;
    padding-left: 8px;
    border-left: 2px solid var(--line);
  }
  .row.compact {
    padding: 5px 10px 5px 14px;
  }
  .empty {
    padding: 20px 8px;
    text-align: center;
  }
</style>
