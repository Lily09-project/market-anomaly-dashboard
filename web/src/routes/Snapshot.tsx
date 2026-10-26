import { useContext, useEffect, useRef, useState } from "react";
import { LoaderContext, useDataset, useDocumentTitle } from "../app/hooks";
import { ScrollRegion } from "../components/ScrollRegion";
import { Gate } from "../components/States";
import { downloadText } from "../lib/csv";
import { formatNumber } from "../lib/format";
import { createSnapshot, diffSnapshots, MAX_SNAPSHOT_BYTES, validateSnapshot, type Snapshot, type ValidationResult } from "../lib/snapshot";
import { logReturns } from "../lib/stress";
import type { Backtest, Events, Overview, Provenance, Regimes, Stress } from "../lib/types";
import { useStressWorker } from "../workers/useStressWorker";
import "./Snapshot.css";

interface Data {
  overview: Overview;
  regimes: Regimes;
  backtest: Backtest;
  events: Events;
  stress: Stress;
  provenance: Provenance;
}

function display(value: string | number | null): string {
  if (value === null) return "—";
  if (typeof value === "number") return Math.abs(value) < 10 && !Number.isInteger(value) ? formatNumber(value, 4) : String(value);
  return value;
}

function Creator({ data, schemaVersion }: { data: Data; schemaVersion: string }) {
  const [symbol, setSymbol] = useState(data.overview.symbols[0]?.symbol ?? "");
  const [label, setLabel] = useState("");
  const [created, setCreated] = useState<Snapshot | null>(null);
  const { run, cancel, running, progress, error } = useStressWorker();

  const build = async () => {
    const series = data.overview.symbols.find((s) => s.symbol === symbol)!;
    const params = data.stress.defaults;
    const summary = await run(logReturns(series.close), params);
    const regime = data.regimes.symbols[symbol]!;
    const bt = data.backtest.symbols[symbol]!;
    const negative = data.events.study.negative;
    const snapshot = await createSnapshot({
      label,
      data: { input_sha256: data.provenance.input_sha256, schema_version: schemaVersion, range: data.provenance.range },
      symbol,
      params: { ...params },
      results: {
        regime_state: regime.labels[regime.current.state] ?? String(regime.current.state),
        regime_probability: regime.current.probability,
        regime_accuracy: regime.accuracy,
        pbo: bt.pbo,
        dsr: bt.dsr.dsr,
        walk_forward_sharpe: bt.oos_sharpe_stitched,
        event_post_car_3d: negative.post_car[negative.post_offsets.indexOf(3)] ?? null,
        var95: summary.var95,
        cvar95: summary.cvar95,
        var99: summary.var99,
        cvar99: summary.cvar99,
      },
    });
    setCreated(snapshot);
    downloadText(`snapshot-${symbol}-${snapshot.fingerprint.slice(0, 8)}.json`, JSON.stringify(snapshot, null, 2), "application/json");
  };

  return (
    <section className="card snapshot-card" aria-labelledby="create-title">
      <h2 id="create-title">建立研究快照</h2>
      <p className="muted">快照保存資料指紋、參數與結果。SHA-256 只檢查內容一致性，來源仍需自行確認。</p>
      <div className="controls">
        <label className="field">
          <span className="label">標的</span>
          <select className="input" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {data.overview.symbols.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol} {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field snapshot-label">
          <span className="label">備註（選填，最多 120 字）</span>
          <input className="input" value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)} />
        </label>
        {running ? (
          <button type="button" className="btn" onClick={cancel}>
            取消
          </button>
        ) : (
          <button type="button" className="btn btn-primary" onClick={() => void build().catch(() => undefined)}>
            建立並下載快照
          </button>
        )}
      </div>
      {running && <progress max={1} value={progress} aria-label="壓力測試進度" />}
      {error && <p role="alert">建立失敗：{error}</p>}
      {created && (
        <p className="callout" data-testid="created-snapshot" aria-live="polite">
          已下載 {created.symbol} 的快照。指紋 <code className="mono">{created.fingerprint}</code>
        </p>
      )}
      <p className="muted small">
        壓力測試使用預設參數（{data.stress.defaults.horizon} 天、區塊 {data.stress.defaults.block} 天、{data.stress.defaults.paths.toLocaleString("zh-TW")} 條路徑、種子 {data.stress.defaults.seed}），所以同一份資料一定得到同樣的快照。
      </p>
    </section>
  );
}

function SnapshotInput({ id, label, result, onResult }: { id: string; label: string; result: ValidationResult | null; onResult: (result: ValidationResult | null) => void }) {
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);
  return (
    <div className="field snapshot-input">
      <label htmlFor={id} className="label">
        {label}
      </label>
      <input
        id={id}
        type="file"
        accept="application/json,.json"
        onChange={(e) => {
          const request = ++generation.current;
          onResult(null);
          const file = e.target.files?.[0];
          if (!file) return;
          // Reject oversized files before reading them into memory.
          if (file.size > MAX_SNAPSHOT_BYTES) {
            onResult({ ok: false, reason: `檔案超過 ${MAX_SNAPSHOT_BYTES / 1024} KB 上限` });
            return;
          }
          file
            .text()
            .then(validateSnapshot)
            .then(
              (validation) => { if (generation.current === request) onResult(validation); },
              () => { if (generation.current === request) onResult({ ok: false, reason: "無法讀取這個檔案" }); },
            );
        }}
      />
      <div aria-live="polite" data-testid={`${id}-status`}>
        {result?.ok && (
          <p className="tag" data-tone="good">
            ✓ 指紋驗證通過：{result.snapshot.symbol}
            {result.snapshot.label ? `（${result.snapshot.label}）` : ""}
          </p>
        )}
        {result && !result.ok && (
          <p className="tag" data-tone="bad" role="alert">
            ✕ 已拒絕：{result.reason}
          </p>
        )}
      </div>
    </div>
  );
}

function Comparer() {
  const [a, setA] = useState<ValidationResult | null>(null);
  const [b, setB] = useState<ValidationResult | null>(null);
  const rows = a?.ok && b?.ok ? diffSnapshots(a.snapshot, b.snapshot) : null;
  const differentData = a?.ok && b?.ok && a.snapshot.data.input_sha256 !== b.snapshot.data.input_sha256;
  return (
    <section className="card snapshot-card" aria-labelledby="compare-title">
      <h2 id="compare-title">驗證與比較快照</h2>
      <p className="muted">檔案只在你的瀏覽器裡讀取與驗證，不會上傳到任何地方；超過 {MAX_SNAPSHOT_BYTES / 1024} KB 或結構不符的檔案會被拒絕。</p>
      <div className="grid grid-2">
        <SnapshotInput id="snapshot-a" label="快照 A" result={a} onResult={setA} />
        <SnapshotInput id="snapshot-b" label="快照 B" result={b} onResult={setB} />
      </div>
      {differentData && <p className="notice">兩份快照來自不同版本的資料（資料指紋不同），差異可能來自資料本身而不是方法。</p>}
      {rows && (
        <ScrollRegion label="快照差異">
          <table data-testid="diff-table">
            <thead>
              <tr>
                <th scope="col">項目</th>
                <th scope="col">快照 A</th>
                <th scope="col">快照 B</th>
                <th scope="col">相同？</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} data-changed={row.changed}>
                  <th scope="row">{row.label}</th>
                  <td className="num">{display(row.a)}</td>
                  <td className="num">{display(row.b)}</td>
                  <td>{row.changed ? <span className="tag" data-tone="warn">不同</span> : "相同"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      )}
    </section>
  );
}

function useSchemaVersion(): string | null {
  const loader = useContext(LoaderContext);
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    if (!loader) return;
    let alive = true;
    loader.manifest().then(
      (m) => alive && setVersion(m.schema_version),
      // Dataset gates show the manifest error; do not leave an unhandled promise.
      () => { if (alive) setVersion(null); },
    );
    return () => {
      alive = false;
    };
  }, [loader]);
  return version;
}

export default function SnapshotPage() {
  useDocumentTitle("研究快照");
  const overview = useDataset("overview.json");
  const regimes = useDataset("regimes.json");
  const backtest = useDataset("backtest.json");
  const events = useDataset("events.json");
  const stress = useDataset("stress.json");
  const provenance = useDataset("provenance.json");
  const schemaVersion = useSchemaVersion();
  return (
    <div className="page stack">
      <header>
        <span className="eyebrow">可重現研究</span>
        <h1>研究快照</h1>
        <p className="lede">封存資料指紋、參數與分析結果，重新匯入後逐項比較。</p>
      </header>
      <Gate<[Overview, Regimes, Backtest, Events, Stress, Provenance]> states={[overview, regimes, backtest, events, stress, provenance]}>
        {(o, r, b, e, s, p) => <Creator data={{ overview: o, regimes: r, backtest: b, events: e, stress: s, provenance: p }} schemaVersion={schemaVersion ?? "2.0"} />}
      </Gate>
      <Comparer />
    </div>
  );
}
