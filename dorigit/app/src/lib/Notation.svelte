<script lang="ts" module>
  // Verovio (LGPL-3.0, npm "verovio", pinned) is loaded on first use: the toolkit is several MB.
  type Toolkit = {
    setOptions(o: Record<string, unknown>): void;
    loadData(mei: string): boolean;
    renderToSVG(page: number): string;
    getPageCount(): number;
  };
  let toolkit: Promise<Toolkit> | null = null;

  function loadToolkit(): Promise<Toolkit> {
    toolkit ??= (async () => {
      const [{ default: createVerovioModule }, { VerovioToolkit }] = await Promise.all([
        import("verovio/wasm"),
        import("verovio/esm"),
      ]);
      const module = await createVerovioModule();
      return new VerovioToolkit(module) as unknown as Toolkit;
    })();
    return toolkit;
  }
</script>

<script lang="ts">
  // Renders MEI (from dorigit-core's notation.rs) as SVG, on a white "paper" in both themes.
  let { mei, label = "" }: { mei: string; label?: string } = $props();

  let width = $state(800);
  let pages = $state<string[]>([]);
  let error = $state<string | null>(null);
  let loading = $state(true);

  $effect(() => {
    const data = mei;
    const w = Math.max(400, Math.round(width));
    loading = true;
    error = null;
    loadToolkit()
      .then((tk) => {
        // one toolkit is shared: set options and render in one go
        tk.setOptions({
          scale: 45,
          pageWidth: Math.round((w * 100) / 45),
          pageMarginLeft: 20,
          pageMarginRight: 20,
          pageMarginTop: 20,
          pageMarginBottom: 20,
          adjustPageHeight: true,
          breaks: "auto",
          header: "none",
          footer: "none",
          svgViewBox: true,
        });
        if (!tk.loadData(data)) throw new Error("Verovio could not read this notation");
        const out: string[] = [];
        for (let p = 1; p <= tk.getPageCount(); p++) out.push(tk.renderToSVG(p));
        if (data === mei) pages = out;
      })
      .catch((e) => (error = String(e)))
      .finally(() => (loading = false));
  });
</script>

<figure class="notation" bind:clientWidth={width}>
  {#if label}<figcaption>{label}</figcaption>{/if}
  {#if error}
    <p class="error">{error}</p>
  {:else if loading && !pages.length}
    <p class="loading">Drawing notation…</p>
  {/if}
  <div class="paper" class:stale={loading && pages.length > 0}>
    {#each pages as svg, i (i)}
      <!-- SVG produced locally by Verovio from our own MEI -->
      {@html svg}
    {/each}
  </div>
</figure>

<style>
  .notation {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  figcaption {
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
  }
  .paper {
    background: #fff;
    color: #000;
    border: 1px solid var(--line);
    border-radius: 6px;
    overflow-x: auto;
  }
  .paper.stale {
    opacity: 0.6;
  }
  .paper :global(svg) {
    display: block;
    width: 100%;
    height: auto;
  }
  .loading {
    font-size: 12px;
    color: var(--muted);
    margin: 0;
  }
  .error {
    color: var(--del);
    font-size: 12px;
    margin: 0;
  }
</style>
