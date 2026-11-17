<script lang="ts">
  import { thumbnailUrl } from "./api";
  import type { Snapshot } from "./types";

  let { snapshot, width = 48 }: { snapshot: Snapshot; width?: number } = $props();
  let url = $state<string | null>(null);

  $effect(() => {
    url = null;
    const s = snapshot;
    thumbnailUrl(s).then((u) => {
      if (s === snapshot) url = u;
    });
  });
</script>

<div class="thumb" style:width="{width}px" style:height="{Math.round(width * 1.32)}px">
  {#if url}
    <img src={url} alt="First page of {snapshot.file_name}" />
  {:else}
    <span class="placeholder">♪</span>
  {/if}
</div>

<style>
  .thumb {
    flex: none;
    border-radius: 4px;
    border: 1px solid var(--line);
    background: white;
    overflow: hidden;
    display: grid;
    place-items: center;
  }
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top;
  }
  .placeholder {
    color: #b8b4aa;
    font-size: 18px;
  }
</style>
