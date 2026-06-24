import { setContext, getContext } from 'svelte';

export type FpThemeId = 'light' | 'dark';

export interface FpThemeContext {
  readonly themeId: FpThemeId;
  setTheme: (id: FpThemeId) => void;
  toggleTheme: () => void;
}

const THEME_KEY = 'fp:theme';

/**
 * Erstellt den Theme-Context und macht ihn via setContext verfügbar.
 * Wird einmal in ThemeProvider.svelte aufgerufen.
 *
 * Kein ThemeState-Class: im frontprompt-Skeleton ist der State
 * einfach genug für eine inline $state-Variable im Provider.
 */
export function createThemeContext(initial: FpThemeId = 'light'): FpThemeContext {
  let themeId = $state<FpThemeId>(initial);

  const context: FpThemeContext = {
    get themeId() {
      return themeId;
    },
    setTheme(id: FpThemeId) {
      themeId = id;
    },
    toggleTheme() {
      themeId = themeId === 'light' ? 'dark' : 'light';
    },
  };

  setContext(THEME_KEY, context);
  return context;
}

/**
 * Holt den Theme-Context aus dem Komponentenbaum.
 * Wirft wenn ausserhalb eines ThemeProviders aufgerufen.
 */
export function getThemeContext(): FpThemeContext {
  const ctx = getContext<FpThemeContext | undefined>(THEME_KEY);
  if (!ctx) {
    throw new Error('getThemeContext() muss innerhalb von <ThemeProvider> aufgerufen werden');
  }
  return ctx;
}
