// ============================================================================
// Content layer — Markdown is the single source of truth.
// ============================================================================
// Every doc page is one of the repo's existing *.md files, imported RAW via
// Vite's import.meta.glob. Nothing here re-types the documentation prose; the
// Svelte layer only renders these strings. The only site-authored Markdown is
// content/landing.md (marketing decomposition that lives nowhere else).
//
// Glob keys are paths relative to THIS file (site/src/lib/content.ts):
//   ../../../            → frontprompt repo root
// ============================================================================

export type NavGroup = 'Overview' | 'Architecture' | 'Guides' | 'Services' | 'Specs' | 'Project';

export interface Doc {
  slug: string;
  title: string;
  group: NavGroup;
  order: number;
  /** Original repo path, e.g. "docs/wire-protocol.md" — shown as a source link. */
  source: string;
  raw: string;
}

const GROUP_ORDER: NavGroup[] = ['Overview', 'Architecture', 'Guides', 'Services', 'Specs', 'Project'];

// Raw Markdown globs. Each pattern is a static string literal so Vite can
// analyse it at build time. eager → values are the file contents directly.
const topLevel = import.meta.glob('../../../*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const docsTree = import.meta.glob('../../../docs/**/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const serviceReadmes = import.meta.glob('../../../frontend/src/services/*/README.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Strip the leading `../../../` so keys read as repo-relative paths. */
function repoPath(globKey: string): string {
  return globKey.replace(/^(\.\.\/)+/, '');
}

function firstHeading(raw: string): string | null {
  const m = raw.match(/^#\s+(.+?)\s*$/m);
  return m ? m[1].trim() : null;
}

function titleCase(slugPart: string): string {
  return slugPart
    .split('-')
    .map((w) => (w.length ? w[0].toUpperCase() + w.slice(1) : w))
    .join(' ');
}

/** Map a repo path to its nav identity. Returns null for files we don't surface. */
function classify(path: string, raw: string): Omit<Doc, 'raw' | 'source'> | null {
  // Top-level docs — curated titles + groups.
  if (path === 'README.md') return { slug: 'overview', title: 'Overview', group: 'Overview', order: 0 };
  if (path === 'ARCHITECTURE.md')
    return { slug: 'architecture', title: 'Architecture', group: 'Architecture', order: 0 };
  if (path === 'DEVELOPMENT.md') return { slug: 'development', title: 'Development', group: 'Project', order: 0 };
  if (path === 'CONTRIBUTING.md') return { slug: 'contributing', title: 'Contributing', group: 'Project', order: 1 };
  if (path === 'CHANGELOG.md') return { slug: 'changelog', title: 'Changelog', group: 'Project', order: 2 };

  // Guides under docs/ (but not the dated specs).
  if (path === 'docs/wire-protocol.md')
    return { slug: 'wire-protocol', title: 'Wire Protocol', group: 'Guides', order: 0 };

  // Dated design specs: docs/specs/YYYY-MM-DD-<name>-design.md
  const spec = path.match(/^docs\/specs\/(\d{4}-\d{2}-\d{2})-(.+?)(?:-design)?\.md$/);
  if (spec) {
    const [, date, name] = spec;
    return {
      slug: `spec-${name}`,
      title: titleCase(name),
      group: 'Specs',
      // newest spec first → negate the date's numeric form for ordering
      order: -Number(date.replace(/-/g, '')),
    };
  }

  // Any other doc directly under docs/ → Guides, titled from its H1.
  const docFile = path.match(/^docs\/([^/]+)\.md$/);
  if (docFile) {
    return { slug: docFile[1], title: firstHeading(raw) ?? titleCase(docFile[1]), group: 'Guides', order: 1 };
  }

  // Frontend in-page services: frontend/src/services/<name>/README.md
  const svc = path.match(/^frontend\/src\/services\/([^/]+)\/README\.md$/);
  if (svc) {
    return { slug: `service-${svc[1]}`, title: svc[1], group: 'Services', order: 0 };
  }

  return null;
}

function buildDocs(): Doc[] {
  const merged: Record<string, string> = { ...topLevel, ...docsTree, ...serviceReadmes };
  const docs: Doc[] = [];
  for (const [globKey, raw] of Object.entries(merged)) {
    const path = repoPath(globKey);
    const id = classify(path, raw);
    if (!id) continue;
    docs.push({ ...id, source: path, raw });
  }
  // Stable sort: by group order, then per-group order, then title.
  docs.sort((a, b) => {
    const g = GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group);
    if (g !== 0) return g;
    if (a.order !== b.order) return a.order - b.order;
    return a.title.localeCompare(b.title);
  });
  return docs;
}

export const docs: Doc[] = buildDocs();

export const docBySlug: Map<string, Doc> = new Map(docs.map((d) => [d.slug, d]));

/** Map of repo path → slug, used to rewrite inter-doc Markdown links to routes. */
export const slugByPath: Map<string, string> = new Map(docs.map((d) => [d.source, d.slug]));

export interface NavSection {
  group: NavGroup;
  docs: Doc[];
}

export const nav: NavSection[] = GROUP_ORDER.map((group) => ({
  group,
  docs: docs.filter((d) => d.group === group),
})).filter((s) => s.docs.length > 0);

export const DEFAULT_DOC = docBySlug.has('overview') ? 'overview' : docs[0]?.slug;

// ----------------------------------------------------------------------------
// Section parsing — feeds the marketing landing from Markdown without re-typing.
// ----------------------------------------------------------------------------

export interface ParsedDoc {
  h1: string | null;
  /** Everything between the H1 and the first H2 (the "lede"). */
  intro: string;
  /** H2 sections keyed by heading text → body Markdown ABOVE any nested H3. */
  sections: Map<string, string>;
  /** Full H2 body keyed by heading text, INCLUDING all nested H3 + their bodies. */
  fullSections: Map<string, string>;
  /** Nested H3 items grouped under their parent H2 heading. */
  subsections: Map<string, { title: string; body: string }[]>;
}

export function parseDoc(raw: string): ParsedDoc {
  const lines = raw.split('\n');
  let h1: string | null = null;
  const introLines: string[] = [];
  const sections = new Map<string, string>();
  const fullSections = new Map<string, string>();
  const subsections = new Map<string, { title: string; body: string }[]>();

  let currentH2: string | null = null;
  let currentH3: { title: string; body: string } | null = null;
  let h2Body: string[] = [];
  let h2Full: string[] = [];

  const flushH3 = () => {
    if (currentH2 && currentH3) {
      const list = subsections.get(currentH2) ?? [];
      currentH3.body = currentH3.body.trim();
      list.push(currentH3);
      subsections.set(currentH2, list);
    }
    currentH3 = null;
  };
  const flushH2 = () => {
    flushH3();
    if (currentH2) {
      sections.set(currentH2, h2Body.join('\n').trim());
      fullSections.set(currentH2, h2Full.join('\n').trim());
    }
    h2Body = [];
    h2Full = [];
  };

  for (const line of lines) {
    const mH1 = line.match(/^#\s+(.+?)\s*$/);
    const mH2 = line.match(/^##\s+(.+?)\s*$/);
    const mH3 = line.match(/^###\s+(.+?)\s*$/);

    if (mH1 && h1 === null && currentH2 === null) {
      h1 = mH1[1].trim();
      continue;
    }
    if (mH2) {
      flushH2();
      currentH2 = mH2[1].trim();
      continue;
    }
    if (mH3 && currentH2) {
      flushH3();
      currentH3 = { title: mH3[1].trim(), body: '' };
      h2Full.push(line);
      continue;
    }

    if (currentH3) {
      currentH3.body += line + '\n';
      h2Full.push(line);
    } else if (currentH2) {
      h2Body.push(line);
      h2Full.push(line);
    } else if (h1 !== null) {
      introLines.push(line);
    }
  }
  flushH2();

  return { h1, intro: introLines.join('\n').trim(), sections, fullSections, subsections };
}

// README is the SSoT for the hero pitch + install + usage on the landing.
const readmeRaw =
  (topLevel['../../../README.md'] as string | undefined) ?? docs.find((d) => d.slug === 'overview')?.raw ?? '';
export const readme: ParsedDoc = parseDoc(readmeRaw);

// landing.md is the SSoT for the marketing-only decomposition (features, steps).
const landingRaw = import.meta.glob('../../content/landing.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
export const landing: ParsedDoc = parseDoc(Object.values(landingRaw)[0] ?? '');

/** Punchy one-line hero subtitle (marketing copy, not the README pitch). */
export const heroSubtitle: string = landing.sections.get('Subtitle') ?? '';

export interface Card {
  title: string;
  body: string;
}

/** Marketing feature cards, authored as H3 items under "## Features" in landing.md. */
export const features: Card[] = landing.subsections.get('Features') ?? [];

/** "How it works" steps, authored as H3 items under "## How it works" in landing.md. */
export const steps: Card[] = landing.subsections.get('How it works') ?? [];
