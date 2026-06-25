// ============================================================================
// Markdown renderer — turns the SSoT *.md strings into HTML.
// ============================================================================
// Two doc-aware concerns beyond plain rendering:
//   1. Inter-doc links (`ARCHITECTURE.md`, `../regions/README.md`, ...) are
//      rewritten to in-site hash routes (#/docs/<slug>) when the target is a
//      doc we surface; external links open in a new tab; unknown repo links
//      fall through to the canonical GitHub blob so nothing 404s.
//   2. Headings get slug ids so deep links (#/docs/architecture#scope) work.
// ============================================================================

import MarkdownIt from 'markdown-it';
import anchor from 'markdown-it-anchor';
import { slugByPath } from './content';
import { BASE } from './routes.svelte';

const GITHUB_BLOB = 'https://github.com/SurrealMindAI/frontprompt/blob/main/';

/** Normalise a relative link against the directory of the doc that contains it. */
function resolveRepoPath(sourcePath: string, href: string): string {
  const baseDir = sourcePath.includes('/') ? sourcePath.replace(/\/[^/]*$/, '') : '';
  const stack = baseDir ? baseDir.split('/') : [];
  for (const part of href.split('/')) {
    if (part === '' || part === '.') continue;
    if (part === '..') stack.pop();
    else stack.push(part);
  }
  return stack.join('/');
}

function isExternal(href: string): boolean {
  return /^[a-z]+:\/\//i.test(href) || href.startsWith('mailto:');
}

export function renderMarkdown(raw: string, sourcePath: string): string {
  const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
    breaks: false,
  });

  md.use(anchor, {
    permalink: anchor.permalink.headerLink({ safariReaderFix: true }),
    slugify: (s: string) =>
      s
        .toLowerCase()
        .trim()
        .replace(/[^\w\s-]/g, '')
        .replace(/\s+/g, '-'),
  });

  // Custom link_open rule: rewrite hrefs.
  const defaultRender =
    md.renderer.rules.link_open ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));

  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const hrefIndex = token.attrIndex('href');
    if (hrefIndex >= 0) {
      const href = token.attrs![hrefIndex][1];

      if (href.startsWith('#')) {
        // in-page anchor — leave as-is
      } else if (isExternal(href)) {
        token.attrSet('target', '_blank');
        token.attrSet('rel', 'noopener noreferrer');
      } else {
        // Repo-relative link. Split off any #fragment.
        const [pathPart, fragment] = href.split('#');
        const resolved = resolveRepoPath(sourcePath, pathPart);
        const slug = slugByPath.get(resolved);
        if (slug) {
          token.attrs![hrefIndex][1] = `#/docs/${slug}${fragment ? '#' + fragment : ''}`;
        } else {
          // Unknown repo file (LICENSE, an image, a not-surfaced doc): point at
          // the canonical GitHub blob so the link always resolves.
          token.attrs![hrefIndex][1] = GITHUB_BLOB + resolved + (fragment ? '#' + fragment : '');
          token.attrSet('target', '_blank');
          token.attrSet('rel', 'noopener noreferrer');
        }
      }
    }
    return defaultRender(tokens, idx, options, env, self);
  };

  // Make relative <img src> resolve to the GitHub raw host (rare in these docs).
  const defaultImage =
    md.renderer.rules.image ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));
  md.renderer.rules.image = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const srcIndex = token.attrIndex('src');
    if (srcIndex >= 0) {
      const src = token.attrs![srcIndex][1];
      if (!isExternal(src) && !src.startsWith(BASE)) {
        const resolved = resolveRepoPath(sourcePath, src);
        // Repo assets are bundled into the site (site/public/assets/**), so serve
        // them locally from the site base — works on the live Pages site AND in
        // local preview, without depending on a pushed GitHub branch. Anything
        // else falls back to the canonical GitHub raw host.
        token.attrs![srcIndex][1] = resolved.startsWith('assets/')
          ? BASE + resolved
          : 'https://raw.githubusercontent.com/SurrealMindAI/frontprompt/main/' + resolved;
      }
    }
    return defaultImage(tokens, idx, options, env, self);
  };

  return md.render(raw);
}

/** Lightweight render for marketing snippets that have no inter-doc links. */
export function renderSnippet(raw: string): string {
  const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
  return md.render(raw);
}

/** Inline render (no wrapping <p>) for single-line bits like the hero lede. */
export function renderInline(raw: string): string {
  const md = new MarkdownIt({ html: true, linkify: true, typographer: true });
  return md.renderInline(raw);
}
