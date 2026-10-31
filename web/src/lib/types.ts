export interface SymbolOverview {
  symbol: string;
  name: string;
  is_control: boolean;
  close: number[];
  total_return: number;
  vol_annual: number;
  sharpe: number;
  max_drawdown: number;
  var95_daily: number;
  cvar95_daily: number;
}

export interface Overview {
  dates: string[];
  symbols: SymbolOverview[];
}

/** [start, end, state], inclusive indexes into the return series (date index − 1). */
export type Segment = [number, number, number];

export interface Regime {
  labels: string[];
  means_annual: number[];
  vol_annual: number[];
  transition: number[][];
  expected_days: number[];
  share: number[];
  log_likelihood: number[];
  segments: Segment[];
  current: { state: number; probability: number };
  bic: Record<string, number>;
  bic_choice: number;
  excluded_jump_days: number;
  accuracy: number | null;
  confusion: number[][] | null;
  truth_segments: Segment[] | null;
}

export interface Regimes {
  labels: string[];
  symbols: Record<string, Regime>;
}

export interface MarketEvent {
  date: string;
  return: number;
  z: number;
  state: number;
  injected: boolean | null;
  car_post: number[] | null;
}

export interface Study {
  n: number;
  offsets: number[];
  car: (number | null)[];
  low: (number | null)[];
  high: (number | null)[];
  post_offsets: number[];
  post_car: (number | null)[];
  post_low: (number | null)[];
  post_high: (number | null)[];
}

export interface Events {
  threshold: number;
  window: [number, number];
  symbols: Record<string, { events: MarketEvent[] }>;
  study: { negative: Study; positive: Study };
  control_events: number;
  validation: {
    injected: number;
    detected: number;
    matched: number;
    recall: number | null;
    precision: number | null;
    truth_rebound: { days: number; per_day: number; jumps_per_stock: number };
  } | null;
}

export interface Fold {
  train_start: string;
  test_start: string;
  test_end: string;
  params: [number, number];
  train_sharpe: number;
  test_sharpe: number;
}

export interface BacktestResult {
  fast: number[];
  slow: number[];
  grid: [number, number][];
  cost_per_trade: number;
  split_date: string;
  is_sharpe: number[];
  oos_sharpe: number[];
  full_sharpe: number[];
  best_is: number;
  best_full: number;
  best_is_oos_rank: number;
  walk_forward: Fold[];
  oos_sharpe_stitched: number;
  buy_hold_sharpe_oos: number;
  equity: { start: string; step: number; walk_forward: number[]; buy_hold: number[] };
  pbo: number;
  logits: number[];
  dsr: { sharpe: number; benchmark_sharpe: number; dsr: number; trials: number };
  max_drawdown_best: number;
  causal_check: string;
}

export interface Backtest {
  symbols: Record<string, BacktestResult>;
}

export interface StressParams {
  horizon: number;
  block: number;
  paths: number;
  seed: number;
}

export interface StressParity extends StressParams {
  symbol: string;
  var95: number;
  cvar95: number;
  var99: number;
  cvar99: number;
  median_last: number;
}

export interface Stress {
  defaults: StressParams;
  parity: StressParity[];
}

export interface Provenance {
  data_source: string;
  provider: string;
  is_simulated: boolean;
  seed: number;
  range: { start: string; end: string };
  trading_days: number;
  symbols: string[];
  source_quality: { source_row_count: number; usable_price_rows: number; excluded_no_trade_rows: number } | null;
  input_sha256: string;
  truth: { regimes: boolean; injected_events: boolean };
  disclaimer: string;
  sources: { label: string; url: string }[];
}

export interface TwseSymbol {
  /** Null when the security was suspended or did not trade that day. */
  close: number | null;
  change: number | null;
  volume_shares: number | null;
  value_twd: number | null;
  /** P/E, yield and P/B are published for listed stocks only, not ETFs. */
  pe: number | null;
  dividend_yield_pct: number | null;
  pb: number | null;
  /** Margin and short balances are in board lots (張). */
  margin_balance: number | null;
  margin_change: number | null;
  short_balance: number | null;
  short_change: number | null;
  cross_check: { finmind_close: number; match: boolean } | null;
}

export interface Twse {
  status: "ok" | "unavailable" | "sample";
  trade_date: string | null;
  symbols: Record<string, TwseSymbol>;
  market: { date: string; taiex: number; change: number | null; value_twd: number | null }[];
  sources: { label: string; url: string }[];
}

/** Row order follows `columns`: code, name, close, change, change_pct, value_twd, pe, dividend_yield_pct, pb, margin_balance, margin_change. */
export type MarketRow = [string, string, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null, number | null];

export interface TwseMarket {
  status: "ok" | "unavailable" | "sample";
  trade_date: string | null;
  columns: string[];
  rows: MarketRow[];
  sources: { label: string; url: string }[];
}

export interface Manifest {
  schema_version: string;
  files: Record<string, string>;
}

export interface DataFiles {
  "overview.json": Overview;
  "regimes.json": Regimes;
  "events.json": Events;
  "backtest.json": Backtest;
  "stress.json": Stress;
  "provenance.json": Provenance;
  "twse.json": Twse;
  "twse_market.json": TwseMarket;
}
