import { lazy, Suspense, useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { LoaderContext, useDocumentTitle, useRoute } from "./app/hooks";
import { PageHead } from "./components/PageHead";
import { Shell } from "./components/Shell";
import { EmptyState, ErrorState, Loading } from "./components/States";
import { createLoader, DeploymentChangedError, type Loader } from "./lib/data";
import { routeToHash, type Route } from "./lib/router";
import type { DataFiles } from "./lib/types";
import Home from "./routes/Home";

const importers = {
  regimes: () => import("./routes/Regimes"),
  events: () => import("./routes/Events"),
  backtest: () => import("./routes/Backtest"),
  stress: () => import("./routes/Stress"),
  market: () => import("./routes/Market"),
  compare: () => import("./routes/Compare"),
  snapshot: () => import("./routes/Snapshot"),
  data: () => import("./routes/DataTrust"),
};
const RegimesPage = lazy(importers.regimes);
const EventsPage = lazy(importers.events);
const BacktestPage = lazy(importers.backtest);
const StressPage = lazy(importers.stress);
const MarketPage = lazy(importers.market);
const ComparePage = lazy(importers.compare);
const SnapshotPage = lazy(importers.snapshot);
const DataTrust = lazy(importers.data);

/** Warm the route chunks once the first screen is idle, so switching tabs does not wait on the network. */
function prefetchRoutes() {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  if (connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType ?? "")) return;
  for (const load of Object.values(importers)) load().catch(() => undefined);
}

/**
 * Data each lazy route gates on. Requesting it as soon as the route is known lets
 * the downloads overlap the route chunk instead of waiting for it; the loader
 * caches the verified promise, so the page reuses it.
 */
const ROUTE_DATA: Partial<Record<Route["name"], (keyof DataFiles)[]>> = {
  regimes: ["overview.json", "regimes.json"],
  events: ["overview.json", "events.json", "regimes.json"],
  backtest: ["overview.json", "backtest.json"],
  stress: ["overview.json", "stress.json"],
  market: ["twse_market.json", "overview.json"],
  compare: ["overview.json"],
  snapshot: ["overview.json", "regimes.json", "backtest.json", "events.json", "stress.json", "provenance.json"],
  data: ["provenance.json", "regimes.json", "events.json"],
};

function NotFound({ path }: { path: string }) {
  useDocumentTitle("找不到這個頁面");
  return (
    <div className="page">
      <PageHead eyebrow="404" title="找不到這個頁面" />
      <EmptyState title="這個網址沒有對應的頁面">
        <p>
          網址 <code>{path}</code> 不存在。<a href={routeToHash({ name: "home" })}>回到總覽</a>
        </p>
      </EmptyState>
    </div>
  );
}

function Routes({ route }: { route: Route }) {

  switch (route.name) {
    case "home":
      return <Home route={route} />;
    case "regimes":
      return <RegimesPage route={route} />;
    case "events":
      return <EventsPage route={route} />;
    case "backtest":
      return <BacktestPage route={route} />;
    case "stress":
      return <StressPage route={route} />;
    case "market":
      return <MarketPage route={route} />;
    case "compare":
      return <ComparePage route={route} />;
    case "snapshot":
      return <SnapshotPage />;
    case "data":
      return <DataTrust />;
    case "not-found":
      return <NotFound path={route.path} />;
  }
}

export default function App({ loader }: { loader?: Loader }) {
  const value = useMemo(() => loader ?? createLoader(import.meta.env.BASE_URL), [loader]);
  const deploymentChanged = useSyncExternalStore(value.subscribe, value.hasDeploymentChanged);
  const [route] = useRoute();
  const key = route.name;
  const previousKey = useRef(key);

  useEffect(() => {
    // Failures surface through the page's own useDataset state, not here.
    for (const file of ROUTE_DATA[key] ?? []) value.load(file).catch(() => undefined);
  }, [value, key]);

  useEffect(() => {
    const idle = window.requestIdleCallback;
    if (idle) {
      const id = idle(prefetchRoutes, { timeout: 4000 });
      return () => window.cancelIdleCallback(id);
    }
    const id = window.setTimeout(prefetchRoutes, 2000);
    return () => window.clearTimeout(id);
  }, []);

  // The shell is available even when the next route's module is still loading.
  useEffect(() => {
    if (previousKey.current === key) return;
    previousKey.current = key;
    window.scrollTo({ top: 0 });
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [key]);

  return (
    <LoaderContext.Provider value={value}>
      <Shell>
        <Suspense
          fallback={
            <div className="page">
              <Loading label="頁面載入中" />
            </div>
          }
        >
          {deploymentChanged ? (
            <div className="page"><ErrorState error={new DeploymentChangedError()} /></div>
          ) : <Routes route={route} />}
        </Suspense>
      </Shell>
    </LoaderContext.Provider>
  );
}
