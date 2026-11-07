import { lazy, Suspense, useEffect, useMemo, useRef } from "react";
import { LoaderContext, useRoute } from "./app/hooks";
import { Shell } from "./components/Shell";
import { EmptyState, Loading } from "./components/States";
import { createLoader, type Loader } from "./lib/data";
import { routeToHash, type Route } from "./lib/router";
import Home from "./routes/Home";

const RegimesPage = lazy(() => import("./routes/Regimes"));
const EventsPage = lazy(() => import("./routes/Events"));
const BacktestPage = lazy(() => import("./routes/Backtest"));
const StressPage = lazy(() => import("./routes/Stress"));
const MarketPage = lazy(() => import("./routes/Market"));
const SnapshotPage = lazy(() => import("./routes/Snapshot"));
const DataTrust = lazy(() => import("./routes/DataTrust"));

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
    case "snapshot":
      return <SnapshotPage />;
    case "data":
      return <DataTrust />;
    case "not-found":
      return (
        <div className="page">
          <EmptyState title="找不到這個頁面">
            <p>
              網址 <code>{route.path}</code> 不存在。<a href={routeToHash({ name: "home" })}>回到總覽</a>
            </p>
          </EmptyState>
        </div>
      );
  }
}

export default function App({ loader }: { loader?: Loader }) {
  const value = useMemo(() => loader ?? createLoader(import.meta.env.BASE_URL), [loader]);
  const [route] = useRoute();
  const key = route.name;
  const previousKey = useRef(key);

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
          <Routes route={route} />
        </Suspense>
      </Shell>
    </LoaderContext.Provider>
  );
}
