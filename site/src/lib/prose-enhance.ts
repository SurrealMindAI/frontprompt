// ============================================================================
// Prose enhancement — runs after the Markdown HTML lands in the DOM.
// ============================================================================
// markdown-it gives us static HTML. Four things are nicer done on the live DOM:
//   1. Mermaid code blocks (```mermaid) → rendered SVG diagrams.
//   2. Code blocks → a hover "copy" button.
//   3. Heading-anchor links (markdown-it-anchor) → routed through the hash
//      router so a click deep-links instead of dropping to the landing page.
//   4. Headings (h2/h3) → harvested into an on-this-page table of contents.
// ============================================================================

export interface Heading {
  id: string;
  text: string;
  level: number;
}

let mermaidReady: Promise<typeof import('mermaid').default> | null = null;

function loadMermaid(): Promise<typeof import('mermaid').default> {
  if (!mermaidReady) {
    mermaidReady = import('mermaid').then(async ({ default: mermaid }) => {
      // ELK layout engine — cleaner routing for subgraph-heavy flowcharts (e.g. the
      // ADR relationship graph) than the default dagre. Register before initialize;
      // diagrams opt in via `%%{init: {"layout": "elk"}}%%`.
      const { default: elkLayouts } = await import('@mermaid-js/layout-elk');
      mermaid.registerLayoutLoaders(elkLayouts);
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        themeVariables: {
          background: '#0b0f17',
          primaryColor: '#121826',
          primaryBorderColor: '#5b9dff',
          primaryTextColor: '#e8edf6',
          secondaryColor: '#0e131d',
          tertiaryColor: '#0e131d',
          lineColor: '#7da6e8',
          fontFamily: "'Space Mono', monospace",
          fontSize: '14px',
        },
      });
      return mermaid;
    });
  }
  return mermaidReady;
}

let diagramSeq = 0;

async function renderMermaid(root: HTMLElement): Promise<void> {
  const blocks = Array.from(root.querySelectorAll<HTMLElement>('code.language-mermaid'));
  if (blocks.length === 0) return;
  const mermaid = await loadMermaid();
  for (const code of blocks) {
    const pre = code.closest('pre');
    if (!pre) continue;
    const source = code.textContent ?? '';
    const id = `fp-mermaid-${diagramSeq++}`;
    try {
      const { svg } = await mermaid.render(id, source);
      const figure = document.createElement('div');
      figure.className = 'mermaid-diagram';
      figure.innerHTML = svg;
      pre.replaceWith(figure);
    } catch {
      pre.classList.add('mermaid-error');
    }
  }
}

function addCopyButtons(root: HTMLElement): void {
  const blocks = Array.from(root.querySelectorAll<HTMLPreElement>('pre'));
  for (const pre of blocks) {
    if (pre.dataset.copyReady === '1') continue;
    if (pre.querySelector('code.language-mermaid')) continue;
    pre.dataset.copyReady = '1';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.textContent = 'copy';
    btn.setAttribute('aria-label', 'Copy code to clipboard');
    btn.addEventListener('click', async () => {
      const text = pre.querySelector('code')?.textContent ?? pre.textContent ?? '';
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = 'copied';
        btn.classList.add('ok');
        setTimeout(() => {
          btn.textContent = 'copy';
          btn.classList.remove('ok');
        }, 1400);
      } catch {
        btn.textContent = 'failed';
        setTimeout(() => (btn.textContent = 'copy'), 1400);
      }
    });
    pre.appendChild(btn);
  }
}

function routeHeadingAnchors(root: HTMLElement, slug: string): void {
  const anchors = root.querySelectorAll<HTMLAnchorElement>(
    'h1 > a.header-anchor, h2 > a.header-anchor, h3 > a.header-anchor, h4 > a.header-anchor',
  );
  anchors.forEach((a) => {
    const href = a.getAttribute('href') ?? '';
    if (href.startsWith('#') && !href.startsWith('#/')) {
      a.setAttribute('href', `#/docs/${slug}${href}`);
    }
  });
}

function harvestToc(root: HTMLElement): Heading[] {
  const heads = Array.from(root.querySelectorAll<HTMLHeadingElement>('h2[id], h3[id]'));
  return heads.map((h) => ({
    id: h.id,
    text: (h.textContent ?? '').trim(),
    level: Number(h.tagName.slice(1)),
  }));
}

/** Enhance a rendered `.prose` element. Returns its on-this-page headings. */
export async function enhanceProse(root: HTMLElement, slug: string): Promise<Heading[]> {
  routeHeadingAnchors(root, slug);
  addCopyButtons(root);
  const toc = harvestToc(root);
  await renderMermaid(root); // async last — TOC/buttons shouldn't wait on it
  return toc;
}
