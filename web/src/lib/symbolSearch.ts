/** Ranking and recent-history helpers for the symbol search box. */

export interface SymbolOption {
  symbol: string;
  name: string;
  /** Latest close, shown beside the option. */
  close?: number;
  /** Latest daily change as a fraction (0.01 = +1%). */
  change?: number | null;
  isControl?: boolean;
}

const FULL_WIDTH = new RegExp("[\\uFF01-\\uFF5E]", "g");
const IDEOGRAPHIC_SPACE = new RegExp("\\u3000", "g");

/** Full-width digits and letters (e.g. from a CJK IME) behave like their ASCII forms. */
export function normalizeQuery(text: string): string {
  return text
    .replace(FULL_WIDTH, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(IDEOGRAPHIC_SPACE, " ")
    .trim()
    .toLowerCase();
}

/**
 * Filter and order options for a query: exact code, then code prefix, then name
 * prefix, then any other match. Ties keep the original (data) order.
 */
export function rankSymbols<T extends SymbolOption>(options: readonly T[], query: string): T[] {
  const q = normalizeQuery(query);
  if (!q) return [...options];
  const terms = q.split(/\s+/);
  const scored: { option: T; score: number; index: number }[] = [];
  options.forEach((option, index) => {
    const code = option.symbol.toLowerCase();
    const name = option.name.toLowerCase();
    const haystack = `${code} ${name}`;
    if (!terms.every((term) => haystack.includes(term))) return;
    const score = code === q ? 0 : code.startsWith(q) ? 1 : name.startsWith(q) ? 2 : 3;
    scored.push({ option, score, index });
  });
  return scored.sort((a, b) => a.score - b.score || a.index - b.index).map((s) => s.option);
}

const RECENT_KEY = "mrl:recent-symbols";
export const RECENT_LIMIT = 5;

/** Recently chosen symbols, newest first. Storage can be missing or blocked; that is not an error. */
export function readRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((s): s is string => typeof s === "string").slice(0, RECENT_LIMIT) : [];
  } catch {
    return [];
  }
}

export function pushRecent(symbol: string): string[] {
  const next = [symbol, ...readRecent().filter((s) => s !== symbol)].slice(0, RECENT_LIMIT);
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // Private mode or blocked storage: the list simply is not remembered.
  }
  return next;
}

/** With an empty query, recent symbols lead and the rest follow in data order. */
export function withRecentFirst<T extends SymbolOption>(options: readonly T[], recent: readonly string[]): { option: T; recent: boolean }[] {
  const lookup = new Map(options.map((o) => [o.symbol, o]));
  const head = recent.map((s) => lookup.get(s)).filter((o): o is T => o !== undefined);
  const seen = new Set(head.map((o) => o.symbol));
  return [...head.map((option) => ({ option, recent: true })), ...options.filter((o) => !seen.has(o.symbol)).map((option) => ({ option, recent: false }))];
}
