import type { ReactNode } from "react";
import { useDataset, useRoute } from "../app/hooks";
import { routeToHash, type Route } from "../lib/router";
import "./Shell.css";

/** Navigation keeps the selected symbol, so switching pages never loses context. */
function navItems(symbol: string | undefined): { route: Route; label: string; match: Route["name"][] }[] {
  return [
    { route: { name: "home", symbol }, label: "總覽", match: ["home"] },
    { route: { name: "regimes", symbol }, label: "市場狀態", match: ["regimes"] },
    { route: { name: "events", symbol }, label: "異常事件", match: ["events"] },
    { route: { name: "backtest", symbol }, label: "誠實回測", match: ["backtest"] },
    { route: { name: "stress", symbol }, label: "壓力測試", match: ["stress"] },
    { route: { name: "snapshot" }, label: "研究快照", match: ["snapshot"] },
    { route: { name: "data" }, label: "資料可信度", match: ["data"] },
  ];
}

export function Shell({ children }: { children: ReactNode }) {
  const [route] = useRoute();
  const provenance = useDataset("provenance.json");
  const simulated = provenance.status === "ready" ? provenance.data.is_simulated : null;
  const symbol = "symbol" in route ? route.symbol : undefined;

  return (
    <>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        跳到主要內容
      </a>
      <header className="site-header">
        <div className="site-header-inner">
          <a className="brand" href={routeToHash({ name: "home" })}>
            <span className="brand-mark" aria-hidden="true">MRL</span>
            <span className="brand-text">
              <strong>Market Regime Lab</strong>
              <span>市場狀態實驗室</span>
            </span>
          </a>
          <nav aria-label="主要頁面" className="site-nav">
            <ul>
              {navItems(symbol).map((item) => (
                <li key={item.label}>
                  <a href={routeToHash(item.route)} aria-current={item.match.includes(route.name) ? "page" : undefined}>
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="site-tools">
            {simulated !== null && (
              <a className="data-badge" href={routeToHash({ name: "data" })} data-simulated={simulated} data-testid="data-badge">
                {simulated ? "合成資料" : "市場資料"}
              </a>
            )}
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <footer className="site-footer">
        <div className="site-footer-inner">
          <p>
            {provenance.status === "ready" && (
              <>
                資料期間 {provenance.data.range.start} 至 {provenance.data.range.end}，共 {provenance.data.trading_days} 個交易日
                {provenance.data.is_simulated ? "（固定種子的合成行情，含已知答案供驗證）" : ""}。
              </>
            )}
            本站僅供研究與教學，不構成任何投資建議；所有績效與風險數字都是歷史或模擬結果，不代表未來表現。
          </p>
          <p className="muted">
            <a href={routeToHash({ name: "data" })}>方法、限制與資料完整性</a>
          </p>
        </div>
      </footer>
    </>
  );
}
