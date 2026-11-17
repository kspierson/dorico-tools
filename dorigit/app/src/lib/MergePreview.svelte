<script lang="ts">
  // Merge preview (docs/MERGE.md §4): what combining two versions would do. Read-only.
  import type { MergeItem, MergeLane, MergePreview } from "./types";

  let {
    preview,
    oursLabel,
    theirsLabel,
  }: { preview: MergePreview; oursLabel: string; theirsLabel: string } = $props();

  const LANE: Record<MergeLane, string> = {
    structure: "Structure",
    music: "Music",
    orchestration: "Orchestration",
    engraving: "Engraving",
    settings: "Settings",
    playback: "Playback",
  };

  let conflicts = $derived(preview.items.filter((i) => i.outcome === "conflict"));
  let reviews = $derived(preview.items.filter((i) => i.outcome === "review"));
  let autos = $derived(preview.items.filter((i) => i.outcome === "auto"));

  function place(i: MergeItem): string {
    const parts = [i.flow, i.owner, i.voice].filter(Boolean);
    if (i.bar) parts.push(`b. ${i.bar}`);
    return parts.join(" · ");
  }

  function sideLabel(i: MergeItem): string {
    return i.side === "ours" ? oursLabel : i.side === "theirs" ? theirsLabel : "both";
  }
</script>

{#snippet item(i: MergeItem)}
  <li class="item {i.outcome}">
    <div class="where">
      <span class="lane">{LANE[i.lane]}</span>
      <span class="place">{place(i)}</span>
      {#if i.outcome !== "conflict"}<span class="muted small">({sideLabel(i)})</span>{/if}
    </div>
    {#if i.reason}<p class="reason">{i.reason}</p>{/if}
    <div class="sides" class:single={!i.ours.length || !i.theirs.length}>
      {#if i.ours.length}
        <div>
          <span class="who">{oursLabel}</span>
          {#each i.ours as l}<div class="line">{l}</div>{/each}
        </div>
      {/if}
      {#if i.theirs.length}
        <div>
          <span class="who">{theirsLabel}</span>
          {#each i.theirs as l}<div class="line">{l}</div>{/each}
        </div>
      {/if}
    </div>
  </li>
{/snippet}

<div class="merge">
  <div class="counts">
    <span class="c conflict">{preview.counts.conflict} conflict{preview.counts.conflict === 1 ? "" : "s"}</span>
    <span class="c review">{preview.counts.review} to review</span>
    <span class="c auto">{preview.counts.auto} automatic</span>
    <span class="c same">{preview.counts.same} identical on both</span>
  </div>
  <p class="muted small">
    Preview only: nothing is changed. Applying a merge comes later (it needs the engine's editing layer).
  </p>

  {#each preview.integrity as p}
    <p class="warn small">⚠ {p}</p>
  {/each}

  {#if preview.structure.length}
    <h4>Structure</h4>
    <ul class="plain">
      {#each preview.structure as s}
        <li class="small">
          {s.flow}: {s.text} <span class="muted">({s.side === "ours" ? oursLabel : s.side === "theirs" ? theirsLabel : "both"})</span>
        </li>
      {/each}
    </ul>
  {/if}

  {#if conflicts.length}
    <h4>Conflicts <span class="muted">· choose a version</span></h4>
    <ul class="plain">{#each conflicts as i, k (k)}{@render item(i)}{/each}</ul>
  {/if}

  {#if reviews.length}
    <h4>To review <span class="muted">· combinable, but check it's what you want</span></h4>
    <ul class="plain">{#each reviews as i, k (k)}{@render item(i)}{/each}</ul>
  {/if}

  {#if autos.length}
    <details>
      <summary><h4>Automatic <span class="muted">· only one version changed these ({autos.length})</span></h4></summary>
      <ul class="plain">{#each autos.slice(0, 300) as i, k (k)}{@render item(i)}{/each}</ul>
      {#if autos.length > 300}<p class="muted small">… and {autos.length - 300} more</p>{/if}
    </details>
  {/if}

  {#if !conflicts.length && !reviews.length && !autos.length}
    <p class="muted">Nothing to merge: the versions don't differ from their common starting point in different ways.</p>
  {/if}
</div>

<style>
  .merge {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .counts {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .c {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
  }
  .c.conflict {
    background: var(--del-soft);
    color: var(--del);
  }
  .c.review {
    background: var(--amber-soft);
    color: var(--amber);
  }
  .c.auto {
    background: var(--add-soft);
    color: var(--add);
  }
  .c.same {
    background: var(--panel-2);
    color: var(--muted);
  }
  h4 {
    margin: 8px 0 4px;
    font-size: 13px;
    display: inline;
  }
  summary {
    cursor: pointer;
  }
  .plain {
    list-style: none;
    padding: 0;
    margin: 4px 0 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .item {
    border: 1px solid var(--line);
    border-left: 3px solid var(--line);
    border-radius: 6px;
    padding: 6px 10px;
    background: var(--panel);
  }
  .item.conflict {
    border-left-color: var(--del);
  }
  .item.review {
    border-left-color: var(--amber);
  }
  .item.auto {
    border-left-color: var(--add);
  }
  .where {
    display: flex;
    gap: 8px;
    align-items: baseline;
    flex-wrap: wrap;
    font-size: 13px;
  }
  .lane {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
  }
  .place {
    font-weight: 600;
  }
  .reason {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--muted);
  }
  .sides {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 4px;
  }
  .sides.single {
    grid-template-columns: 1fr;
  }
  .who {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
  }
  .line {
    font-size: 12px;
    font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
    word-break: break-word;
  }
  .small {
    font-size: 12px;
  }
  .warn {
    color: var(--amber);
    margin: 0;
  }
  p {
    margin: 0;
  }
</style>
