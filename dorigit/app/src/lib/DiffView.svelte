<script lang="ts">
  import Notation from "./Notation.svelte";
  import { inTauri } from "./api";
  import { prettyDetail, prettyProp } from "./format";
  import type { DiffNotation, EventChange, ScoreDiff, SettingChange } from "./types";

  let {
    diff,
    notation,
  }: {
    diff: ScoreDiff;
    /** Fetch before/after notation for a flow; omit to hide the Notation buttons. */
    notation?: (flowId: string) => Promise<DiffNotation>;
  } = $props();

  // flow id -> notation (or the error), for flows whose notation is shown
  let shown = $state<Record<string, DiffNotation | string | null>>({});

  async function toggleNotation(flowId: string) {
    if (flowId in shown) {
      delete shown[flowId];
      return;
    }
    shown[flowId] = null;
    try {
      shown[flowId] = await notation!(flowId);
    } catch (e) {
      shown[flowId] = String(e);
    }
  }

  // browser preview only: "#notation" opens the first flow's notation (for screenshots)
  $effect(() => {
    if (!inTauri && notation && location.hash === "#notation" && musicalFlows[0] && !(musicalFlows[0].flow_id in shown))
      toggleNotation(musicalFlows[0].flow_id);
  });

  function barsLabel(b: [string, string] | null): string {
    return b ? (b[0] === b[1] ? `b. ${b[0]}` : `b. ${b[0]}–${b[1]}`) : "";
  }

  const ICON = { added: "+", removed: "−", modified: "~" } as const;

  // dorigit-core tidy.rs: a version saved by a newer Dorico has its format-only changes hidden
  const RESAVED = "Re-saved in Dorico";
  let resaved = $derived(diff.info.find((i) => i.key === RESAVED) ?? null);
  let info = $derived(diff.info.filter((i) => i.key !== RESAVED));

  let musicalFlows = $derived(diff.flows.filter((f) => f.change !== "modified" || f.total > 0 || f.meters || f.video || f.old_name));
  let counts = $derived.by(() => {
    const c = { added: 0, removed: 0, modified: 0 };
    for (const f of diff.flows) for (const o of f.owners) for (const e of o.changes) c[e.change]++;
    return c;
  });
  let nothing = $derived(
    !musicalFlows.length && !diff.players.length && !diff.info.filter((i) => i.key !== "Re-saved in Dorico").length && !diff.options.length && !diff.layouts.length,
  );

  function what(e: EventChange): string {
    return e.text ? `${e.kind} ${e.text}` : e.kind;
  }

  function settingLabel(s: SettingChange): string {
    const tidy = (p: string) => p.replace(/^array\//, "").replaceAll("/", " › ");
    switch (s.type) {
      case "value":
        return `${tidy(s.path)}: ${s.old ?? "(none)"} → ${s.new ?? "(none)"}`;
      case "item_added":
        return `Added ${tidy(s.path)}${s.name ? ` (${s.name})` : ""}`;
      case "item_removed":
        return `Removed ${tidy(s.path)}${s.name ? ` (${s.name})` : ""}`;
    }
  }
</script>

<div class="diff">
  {#if resaved}
    <p class="resaved">
      Saved with a newer Dorico ({resaved.old} → {resaved.new.replace(/ \(.*$/, "")}).
      {resaved.new.match(/\((.*)\)/)?.[1] ?? ""}: settings Dorico added or rewrote by itself, not your edits.
    </p>
  {/if}
  {#if nothing}
    <p class="muted">No musical changes: only save details (date, file name) differ.</p>
  {:else}
    {#if counts.added + counts.removed + counts.modified > 0}
      <div class="counts">
        <span class="c added">+{counts.added} added</span>
        <span class="c removed">−{counts.removed} removed</span>
        <span class="c modified">~{counts.modified} changed</span>
      </div>
    {/if}


    {#if info.length}
      <h4>Project info</h4>
      <ul class="plain">
        {#each info as i}
          <li><b>{i.key}</b>: “{i.old}” → “{i.new}”</li>
        {/each}
      </ul>
    {/if}

    {#if diff.players.length}
      <h4>Players</h4>
      <ul class="plain">
        {#each diff.players as p}
          <li class={p.change}>
            <span class="icon">{ICON[p.change]}</span>
            {#if p.change === "added"}{p.new} added{:else if p.change === "removed"}{p.old} removed{:else}{p.old} renamed to {p.new}{/if}
          </li>
        {/each}
      </ul>
    {/if}

    {#each musicalFlows as f (f.flow_id)}
      <div class="flow">
        <div class="flow-head">
          <span class="flow-name">{f.old_name ? `${f.old_name} → ${f.name}` : f.name}</span>
          {#if f.change === "added"}
            <span class="tag added">new flow</span>
          {:else if f.change === "removed"}
            <span class="tag removed">flow removed</span>
          {:else}
            <span class="muted">{f.total} change{f.total === 1 ? "" : "s"}</span>
          {/if}
          {#if notation && f.change === "modified" && f.total > 0}
            <button class="small-btn" onclick={() => toggleNotation(f.flow_id)}>
              {f.flow_id in shown ? "Hide notation" : "Show notation"}
            </button>
          {/if}
        </div>
        {#if f.flow_id in shown}
          {@const n = shown[f.flow_id]}
          <div class="notation-pair">
            {#if n === null}
              <p class="muted small">Preparing notation…</p>
            {:else if typeof n === "string"}
              <p class="error small">{n}</p>
            {:else}
              <p class="muted small legend">
                <span class="dot added"></span> added <span class="dot modified"></span> changed
                <span class="dot removed"></span> removed · only players with changes · concert pitch{n.truncated
                  ? " · first 12 changed bars"
                  : ""}
              </p>
              {#if n.before}<Notation mei={n.before} label={`Before (${barsLabel(n.before_bars)})`} />{/if}
              {#if n.after}<Notation mei={n.after} label={`After (${barsLabel(n.after_bars)})`} />{/if}
            {/if}
          </div>
        {/if}
        {#if f.meters}
          <div class="meters muted">Time signatures: {f.meters[0].join(", ")} → {f.meters[1].join(", ")}</div>
        {/if}
        {#if f.video}
          <div class="meters muted">Picture: {f.video[0]} → {f.video[1]}</div>
        {/if}
        {#each f.owners as o (o.owner)}
          <details open={f.owners.length <= 6 || o.changes.length <= 3}>
            <summary>
              <span class="owner">{o.owner}</span>
              <span class="muted">{o.changes.length}</span>
            </summary>
            <ul>
              {#each o.changes.slice(0, 300) as e, i (i)}
                <li class={e.change}>
                  <span class="icon">{ICON[e.change]}</span>
                  <span class="where">{e.where.replace("bar ", "b. ").replace(" beat ", " · ")}</span>
                  <span class="what">
                    {what(e)}
                    {#if e.lane}<span class="lane">{e.lane}</span>{/if}
                    {#if e.change === "modified"}
                      <span class="detail">{e.details.map(prettyDetail).join("; ")}</span>
                    {:else if e.props.length}
                      <span class="detail">{e.props.map(prettyProp).join("; ")}</span>
                    {/if}
                  </span>
                </li>
              {/each}
              {#if o.changes.length > 300}
                <li class="muted">… and {o.changes.length - 300} more</li>
              {/if}
            </ul>
          </details>
        {/each}
      </div>
    {/each}

    {#each [{ label: "Engraving & notation options", list: diff.options }, { label: "Layouts", list: diff.layouts }] as group}
      {#if group.list.length}
        <details class="settings">
          <summary>{group.label} <span class="muted">{group.list.length}</span></summary>
          <ul class="plain small">
            {#each group.list.slice(0, 200) as s}
              <li>{settingLabel(s)}</li>
            {/each}
            {#if group.list.length > 200}<li class="muted">… and {group.list.length - 200} more</li>{/if}
          </ul>
        </details>
      {/if}
    {/each}
  {/if}
</div>

<style>
  .diff {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .counts {
    display: flex;
    gap: 8px;
  }
  .c {
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
  }
  .c.added {
    background: var(--add-soft);
    color: var(--add);
  }
  .c.removed {
    background: var(--del-soft);
    color: var(--del);
  }
  .c.modified {
    background: var(--mod-soft);
    color: var(--mod);
  }
  h4 {
    margin: 6px 0 0;
    font-size: 13px;
  }
  .flow {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 10px 12px;
  }
  .flow-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 4px;
  }
  .flow-name {
    font-weight: 650;
  }
  .resaved {
    font-size: 13px;
    background: var(--amber-soft);
    border-left: 3px solid var(--amber);
    border-radius: 6px;
    padding: 8px 12px;
    margin: 0 0 10px;
  }
  .flow-head .small-btn {
    margin-left: auto;
    padding: 2px 8px;
    font-size: 12px;
  }
  .notation-pair {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin: 6px 0 10px;
  }
  .legend {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
    margin: 0;
  }
  .small {
    font-size: 12px;
  }
  .error {
    color: var(--del);
  }
  .dot {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    margin-left: 6px;
  }
  /* the same colours as notation.rs ADDED / CHANGED / REMOVED (notes are drawn on white) */
  .dot.added {
    background: #2f9e44;
  }
  .dot.modified {
    background: #3b5bdb;
  }
  .dot.removed {
    background: #c92a2a;
  }
  .tag {
    font-size: 12px;
    padding: 1px 6px;
    border-radius: 4px;
  }
  .tag.added {
    background: var(--add-soft);
    color: var(--add);
  }
  .tag.removed {
    background: var(--del-soft);
    color: var(--del);
  }
  .meters {
    font-size: 12px;
    margin-bottom: 4px;
  }
  details {
    border-top: 1px solid var(--line);
    padding: 6px 0 2px;
  }
  details:first-of-type {
    border-top: none;
  }
  summary {
    cursor: pointer;
    display: flex;
    gap: 8px;
    align-items: baseline;
    list-style-position: outside;
  }
  .owner {
    font-weight: 550;
  }
  ul {
    list-style: none;
    margin: 6px 0 4px;
    padding: 0;
  }
  li {
    display: flex;
    gap: 8px;
    align-items: baseline;
    padding: 2px 0;
    font-size: 13px;
    line-height: 1.4;
  }
  .icon {
    flex: none;
    width: 16px;
    text-align: center;
    font-weight: 700;
  }
  li.added .icon {
    color: var(--add);
  }
  li.removed .icon {
    color: var(--del);
  }
  li.modified .icon {
    color: var(--mod);
  }
  li.removed .what {
    text-decoration: line-through;
    text-decoration-color: color-mix(in srgb, var(--del) 50%, transparent);
  }
  .where {
    flex: none;
    width: 92px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    font-size: 12px;
  }
  .what {
    min-width: 0;
  }
  .lane {
    margin-left: 6px;
    font-size: 11px;
    color: var(--muted);
  }
  .detail {
    display: block;
    color: var(--muted);
    font-size: 12px;
  }
  .plain li {
    display: list-item;
  }
  .settings summary {
    font-weight: 550;
  }
  .small li {
    font-size: 12px;
    word-break: break-word;
  }
</style>
