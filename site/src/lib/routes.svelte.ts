// ============================================================================
// Hash router — GitHub Pages is static, so we route on location.hash.
// ============================================================================
//   #/                     → landing
//   #/docs                 → docs (default doc)
//   #/docs/<slug>          → a specific doc
//   #/docs/<slug>#anchor   → doc + scroll to heading anchor
// ============================================================================

import { DEFAULT_DOC } from './content';

export const BASE = import.meta.env.BASE_URL; // '/frontprompt/' in prod, '/' in dev

export type Route =
  | { kind: 'landing' }
  | { kind: 'docs'; slug: string; anchor: string | null };

function parse(hash: string): Route {
  const raw = hash.replace(/^#/, '');
  if (raw === '' || raw === '/') return { kind: 'landing' };

  const m = raw.match(/^\/docs(?:\/([^#]*))?(?:#(.*))?$/);
  if (m) {
    const slug = (m[1] || '').replace(/\/$/, '') || DEFAULT_DOC;
    return { kind: 'docs', slug, anchor: m[2] || null };
  }
  return { kind: 'landing' };
}

class Router {
  route = $state<Route>(parse(typeof location !== 'undefined' ? location.hash : ''));

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('hashchange', () => {
        this.route = parse(location.hash);
        // Defer so the target doc has rendered before we scroll to an anchor.
        if (this.route.kind === 'docs' && this.route.anchor) {
          const id = this.route.anchor;
          requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView());
        } else {
          window.scrollTo({ top: 0 });
        }
      });
    }
  }
}

export const router = new Router();

export function go(hash: string) {
  if (location.hash === hash) {
    // same hash — force a re-scroll to top
    window.scrollTo({ top: 0 });
  } else {
    location.hash = hash;
  }
}
