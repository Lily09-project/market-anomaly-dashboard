import { createContext, useCallback, useContext, useEffect, useState, useSyncExternalStore } from "react";
import type { Loader } from "../lib/data";
import { parseRoute, routeToHash, type Route } from "../lib/router";
import type { DataFiles } from "../lib/types";

export const LoaderContext = createContext<Loader | null>(null);

export type DatasetState<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: Error };

export function useDataset<K extends keyof DataFiles>(name: K): DatasetState<DataFiles[K]>;
export function useDataset<K extends keyof DataFiles>(name: K | null): DatasetState<DataFiles[K]>;
/** Load and verify one data file; pass null to defer loading. */
export function useDataset<K extends keyof DataFiles>(name: K | null): DatasetState<DataFiles[K]> {
  const loader = useContext(LoaderContext);
  const [state, setState] = useState<DatasetState<DataFiles[K]>>({ status: "loading" });
  useEffect(() => {
    if (!loader || name === null) return;
    let alive = true;
    loader.load(name).then(
      (data) => alive && setState({ status: "ready", data }),
      (error: unknown) => alive && setState({ status: "error", error: error instanceof Error ? error : new Error(String(error)) }),
    );
    return () => {
      alive = false;
    };
  }, [loader, name]);
  return state;
}

const subscribeHash = (callback: () => void) => {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
};

export function useRoute(): [Route, (route: Route, options?: { replace?: boolean }) => void] {
  const hash = useSyncExternalStore(subscribeHash, () => window.location.hash, () => "");
  const navigate = useCallback((route: Route, options?: { replace?: boolean }) => {
    const next = routeToHash(route);
    if (options?.replace) {
      window.history.replaceState(null, "", next);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    } else {
      window.location.hash = next;
    }
  }, []);
  return [parseRoute(hash), navigate];
}

export type ThemeChoice = "system" | "light" | "dark";
const THEME_KEY = "market-regime-lab-theme";

function readTheme(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
}

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [theme, setTheme] = useState<ThemeChoice>(readTheme);
  useEffect(() => {
    applyTheme(theme);
    try {
      if (theme === "system") window.localStorage.removeItem(THEME_KEY);
      else window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Storage may be unavailable (private mode); the theme still applies for this visit.
    }
  }, [theme]);
  return [theme, setTheme];
}

/** True when the viewer asked the OS to minimise motion. */
export function usePrefersReducedMotion(): boolean {
  const query = "(prefers-reduced-motion: reduce)";
  return useSyncExternalStore(
    (callback) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", callback);
      return () => media.removeEventListener("change", callback);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title ? `${title}｜Market Regime Lab` : "Market Regime Lab — 市場狀態實驗室";
  }, [title]);
}
