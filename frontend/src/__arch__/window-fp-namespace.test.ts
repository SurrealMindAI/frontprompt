/**
 * Arch test: window.__fp Namespace-Discipline.
 *
 * Hard rule for window-namespace isolation (see ARCHITECTURE.md):
 *
 *     window.__fp ist der **einzige** erlaubte window-global im overlay.
 *
 * Verboten ist alles in der Form ``__fp_<identifier>`` (z.B. __fp_locator,
 * __fp_debug, __fp_helpers, __fp_devtools_x). Auch nicht "nur für DevTools-
 * Debugging" oder "nur in dev-builds". Sub-namespaces gehören an `window.__fp`
 * gehängt (z.B. ``window.__fp.debug.helper``).
 *
 * Warum strikt:
 *   - Overlay läuft auf fremden Pages (example.com, google.com, …) — jede
 *     window-pollution kollidiert potentiell mit host-page-scripts
 *   - Single global = single audit-surface, einfach zu reasonen
 *   - Design intent: keine zig functionen im window — EINEN service
 *
 * Wie der test funktioniert:
 *   Scannt ``src/**\/*.{ts,svelte}`` (außer ``_generated/``, ``__arch__/``,
 *   ``node_modules/``) nach dem token-pattern ``__fp_[a-zA-Z][a-zA-Z0-9_]*``.
 *   Jeder match MUSS in der ``ALLOW_LIST`` registriert sein — sonst fail.
 *
 * Ausnahmen / ALLOW_LIST:
 *   Playwright's ``expose_function`` ZWINGT einen top-level-window-global. Das
 *   ist eine architektonische Einschränkung von Playwright/CDP, kein Bug auf
 *   unserer seite. Daher: das EINE Scaffold ``__fp_internal_state_getter`` wird
 *   in :func:`setupBridge` SOFORT auf ``window.__fp.getState`` migriert + das
 *   original mit ``delete`` entfernt. Im at-rest-state (nach setupBridge) ist
 *   `__fp_internal_state_getter` NICHT mehr im window-namespace.
 *
 * Was du tun musst wenn du ein neues Scaffold brauchst:
 *   1. Frag dich: braucht das wirklich ein eigenes window-global, oder kann's
 *      an `window.__fp.<thing>` hängen? (99% der Fälle: an __fp hängen.)
 *   2. Wenn JA: einen Eintrag in ALLOW_LIST mit JSDoc-Begründung addieren
 *   3. Migration + delete in setupBridge() implementieren
 *   4. Test-rerun
 */

import { describe, expect, test } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, relative, resolve } from 'node:path';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

/**
 * Source-tree-root — alles ab hier wird gescannt.
 *
 * Vitest sets ``process.cwd()`` auf den frontend-package-root (wo vite.config.ts
 * liegt), unabhängig vom test-file-pfad. Daher resolve-from-cwd statt
 * import.meta.url — letzteres ist in jsdom-env nicht zuverlässig.
 */
const SRC_ROOT = resolve(process.cwd(), 'src');

const SCAN_EXTENSIONS = new Set(['.ts', '.svelte']);
const SKIP_DIRS = new Set(['_generated', 'node_modules', '__arch__']);

/**
 * Token-pattern: ``__`` + case-insensitive ``fp`` + null-or-mehr identifier-chars.
 *
 * Strategie: ALLE ``__fp*``-Tokens werden gematcht (auch bare ``__fp`` und
 * uppercase-variants). Im scanner wird dann pro match geprüft:
 *   - Token === lowercase ``__fp``           → ALLOWED (the one true global)
 *   - Token in ALLOW_LIST für diese Datei    → ALLOWED (Playwright-scaffold etc.)
 *   - sonst                                  → VIOLATION
 *
 * Damit gilt: **NUR exact `__fp` (lowercase, kein suffix) ist erlaubt**.
 *
 * Forbidden:
 *   - ``__fp_locator``        underscore-suffix
 *   - ``__fpLocator``         camelCase-suffix
 *   - ``__fp1`` / ``__fp123`` digit-suffix
 *   - ``__fp-debug``          dash (in strings / data-attrs / HTML)
 *   - ``__fp$internal``       dollar
 *   - ``__FP``                bare uppercase (= different global than __fp)
 *   - ``__Fp_anything``       mixed-case prefix
 *
 * Allowed:
 *   - ``__fp`` alleinstehend (vor end-of-token, ``.``, ``(``, ``=`` etc.)
 *   - ``__fp.dispatch`` / ``__fp.getState`` / ``__fp.version`` (method access)
 *   - ``window.__fp = …``     (assignment)
 *   - ``window.__fp(arg)``    (callable invocation)
 *
 * Word-boundary ``\b`` am Anfang verhindert false-positives in längeren
 * identifiers (z.B. ``prefix__fp_x`` matcht nicht).
 *
 * Prefix-case-handling: ``__[Ff][Pp]`` ist case-insensitive ohne ``/i``-flag
 * (die suffix-charset ``[A-Za-z0-9_$-]`` ist sowieso case-tolerant).
 */
export const FORBIDDEN_TOKEN = /\b__[Ff][Pp][A-Za-z0-9_$-]*/g;

/** Das eine erlaubte token. Bare lowercase ``__fp`` — alles andere fail. */
const THE_ONE_ALLOWED_TOKEN = '__fp';

/**
 * ALLOW_LIST: relativer Pfad ab ``src/`` → set erlaubter ``__fp_*``-tokens.
 *
 * Jeder Eintrag MUSS einen begründenden inline-comment in der Source-Datei
 * referenzieren, die erklärt warum Migration+Delete-Pattern nicht ausreicht
 * oder die scaffold-Begründung dokumentiert.
 */
const ALLOW_LIST: Readonly<Record<string, ReadonlySet<string>>> = {
  // Playwright-expose_function-scaffold. setupBridge() migriert + deleted.
  // Siehe bridge.svelte.ts:setupBridge für die Migration-Logik.
  //
  // TOCTOU-Entscheidung — accept as architectural false-positive. Playwright's
  // expose_function kann nur top-level window globals registrieren (CDP
  // constraint, kein frontprompt-Bug). Das Fenster schließt synchron bei
  // DOMContentLoaded; die exponierten Daten (Session-picks/regions/relations)
  // sind keine Credentials.
  // Escape Hatch: UUID-named getter via startup-propagation +
  // page.evaluate seed (kein expose_function mehr) — trigger wenn threat model
  // auf Credentials oder cross-user data expandiert.
  'bridge/bridge.svelte.ts': new Set(['__fp_internal_state_getter']),
  // Kommentar-Referenz auf das oben genannte Scaffold — keine code-usage.
  // Whitelist-Begründung: identisch mit bridge/bridge.svelte.ts-Eintrag.
  'main.ts': new Set(['__fp_internal_state_getter']),
};

// ---------------------------------------------------------------------------
// Scanning logic
// ---------------------------------------------------------------------------

function walkSource(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const path = join(dir, name);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      walkSource(path, out);
    } else if (SCAN_EXTENSIONS.has(extname(name))) {
      out.push(path);
    }
  }
  return out;
}

interface Violation {
  readonly file: string;
  readonly line: number;
  readonly token: string;
  readonly snippet: string;
}

function findViolations(): Violation[] {
  const files = walkSource(SRC_ROOT);
  const violations: Violation[] = [];

  for (const file of files) {
    const rel = relative(SRC_ROOT, file);
    const content = readFileSync(file, 'utf-8');
    const allowed = ALLOW_LIST[rel] ?? new Set<string>();

    for (const match of content.matchAll(FORBIDDEN_TOKEN)) {
      const token = match[0];
      // Bare lowercase ``__fp`` — the one true global, always allowed
      if (token === THE_ONE_ALLOWED_TOKEN) continue;
      // Per-file whitelist (z.B. Playwright-scaffold im setupBridge)
      if (allowed.has(token)) continue;

      const idx = match.index ?? 0;
      const lineNo = content.substring(0, idx).split('\n').length;
      const lines = content.split('\n');
      const snippet = (lines[lineNo - 1] ?? '').trim();
      violations.push({ file: rel, line: lineNo, token, snippet });
    }
  }

  return violations;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('arch: window.__fp namespace discipline', () => {
  test('no __fp_<identifier> token appears outside the ALLOW_LIST', () => {
    const violations = findViolations();

    if (violations.length > 0) {
      const report = violations
        .map(
          (v) =>
            `    ${v.file}:${v.line}\n` +
            `        token:   ${v.token}\n` +
            `        context: ${v.snippet}`
        )
        .join('\n\n');

      throw new Error(
        '\n\n' +
          '═══════════════════════════════════════════════════════════════════════════\n' +
          'ARCH-VIOLATION: window.__fp namespace discipline\n' +
          '═══════════════════════════════════════════════════════════════════════════\n' +
          '\n' +
          'Nur EIN window-global ist erlaubt: window.__fp\n' +
          '\n' +
          'Verboten: __fp_<anything> (z.B. __fp_locator, __fp_debug, __fp_helpers)\n' +
          '\n' +
          'Wenn du was im browser-context exposen willst, häng es an window.__fp\n' +
          '(z.B. window.__fp.debug = {...}) statt ein zweites global zu erstellen.\n' +
          '\n' +
          'Ausnahmen brauchen einen Eintrag in ALLOW_LIST mit JSDoc-Begründung,\n' +
          'in src/__arch__/window-fp-namespace.test.ts.\n' +
          '\n' +
          'Verstöße:\n' +
          report +
          '\n\n' +
          'See: ARCHITECTURE.md, docs/wire-protocol.md\n'
      );
    }

    expect(violations).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // Regex-Self-Test: explizit jede Variante die der user als Schlupfloch nannte
  // -------------------------------------------------------------------------

  /**
   * Klassifiziert einen string: forbidden = mind. 1 match ist NICHT bare ``__fp``.
   * Allow-list wird hier NICHT berücksichtigt — das ist file-level enforcement.
   */
  function classify(input: string): { forbidden: boolean; tokens: string[] } {
    // Fresh regex per call wg. global-flag-lastIndex-state
    const re = /\b__[Ff][Pp][A-Za-z0-9_$-]*/g;
    const tokens = [...input.matchAll(re)].map((m) => m[0]);
    const forbidden = tokens.some((t) => t !== THE_ONE_ALLOWED_TOKEN);
    return { forbidden, tokens };
  }

  describe('regex correctly identifies forbidden variants', () => {
    test.each<[string, string]>([
      ['underscore suffix', 'window.__fp_locator'],
      ['camelCase suffix', 'window.__fpLocator'],
      ['single digit', 'const x = window.__fp1;'],
      ['multi-digit', 'window.__fp123 = {}'],
      ['dash in string-prop access', "window['__fp-debug']"],
      ['dollar suffix', '(window as any).__fp$internal'],
      ['uppercase bare', 'globalThis.__FP'],
      ['uppercase with suffix', 'globalThis.__FP_LOCATOR'],
      ['mixed case prefix', 'window.__Fp_Thing'],
      ['fpExtraLong identifier', 'window.__fpExtraLongHelper'],
      ['trailing underscore alone', 'window.__fp_'],
      ['snake_case suffix', 'window.__fp_internal_debug_helpers'],
      ['as-any-cast escape', '(window as any).__fp_locator'],
      ['string-literal expose name', `page.expose_function("__fp_x", fn)`],
      ['single-letter suffix __fpa', 'const __fpa = false'],
      ['globalThis target', 'globalThis.__fpX = 1'],
      ['self target', 'self.__fp_thing = 1'],
    ])('FORBIDDEN: %s', (_label, source) => {
      const result = classify(source);
      expect(result.forbidden, `expected violation for: ${source}`).toBe(true);
    });

    test.each<[string, string]>([
      ['bare __fp alone', 'const x = window.__fp;'],
      ['method access .dispatch', 'window.__fp.dispatch(msg)'],
      ['method access .getState', 'await window.__fp.getState()'],
      ['property access .version', 'window.__fp.version'],
      ['callable invocation', 'await window.__fp(message)'],
      ['assignment to __fp', 'window.__fp = fp as WindowFp'],
      ['inside-longer-identifier (no boundary)', 'const prefix__fp_x = 1'],
      ['similar-but-unrelated prefix', 'const myFunc = "hello"'],
      ['__fp at end-of-line', 'export const fp = window.__fp;'],
      ['__fp followed by comma', 'fn(a, window.__fp, b)'],
      ['__fp in template-literal interp', 'console.log(`v: ${window.__fp}`)'],
    ])('ALLOWED: %s', (_label, source) => {
      const result = classify(source);
      expect(
        result.forbidden,
        `expected NO violation for: ${source}, got tokens: ${JSON.stringify(result.tokens)}`
      ).toBe(false);
    });
  });

  test('ALLOW_LIST has no dangling references (allowed token must actually appear in file)', () => {
    const dangling: string[] = [];
    for (const [file, tokens] of Object.entries(ALLOW_LIST)) {
      const fullPath = join(SRC_ROOT, file);
      let content: string;
      try {
        content = readFileSync(fullPath, 'utf-8');
      } catch {
        dangling.push(`${file} (file does not exist)`);
        continue;
      }
      for (const token of tokens) {
        if (!content.includes(token)) {
          dangling.push(`${file} → ${token} (allow-list entry but token nowhere in file)`);
        }
      }
    }
    expect(
      dangling,
      'ALLOW_LIST hat veraltete Einträge — entweder Datei umbenennen/Token entfernen oder ALLOW_LIST cleanen:\n' +
        dangling.join('\n')
    ).toEqual([]);
  });
});
