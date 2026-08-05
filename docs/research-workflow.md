# Research Workflow

## 1. Verify Data Before Interpreting It

The workbench starts with the data contract, not a chart. It checks the source label, latest usable trading date, observation count and OHLCV coverage. `ready` means yfinance data contains at least 20 usable closes and complete OHLC values. `caution` means a fallback, sample source, limited history or incomplete field coverage requires conservative interpretation. `unavailable` means the required information is not present and the interface must not imply otherwise.

## 2. Inspect Evidence Instead of a Black-Box Score

The research brief exposes four independent evidence sections:

- **Trend** compares the latest close with MA5, MA20 and MA60.
- **Momentum** describes RSI(14) without converting it into a buy or sell command.
- **Participation** compares current volume with the 20-day average volume.
- **Risk** describes 20-day realised price volatility.

Each section returns `positive`, `neutral`, `risk` or `unavailable`, plus the metrics that caused that state. These are observations about available data, not forecasts.

## 3. Compare Context, Not Just Price

The brief also reports the latest change in price, RSI, MA20 distance and volatility. When at least two comparable peer cards are available, it ranks the selected stock by daily change, 52-week range position and volume ratio. If a metric lacks two valid values, the ranking is not displayed.

## 4. Handle Failure Explicitly

Market-data requests can fail because of network availability, provider limits, market holidays or missing symbols. The application preserves a usable demo path with sample data, but labels it `sample data` in the UI. A fallback is a transparent product state, not hidden production data.

## 5. What This Project Does Not Claim

This project does not predict price direction, calculate target prices, recommend trades or measure investment performance. It is a demonstration of data product engineering: provenance, deterministic transformations, safe degradation, explainable presentation and testable interfaces.
## 6. Preserve Context With an Offline Research Snapshot

A chart screenshot loses the source, data date, fallback status, and inputs that gave an observation meaning. The stock page therefore exports an offline Research Snapshot as JSON and self-contained printable HTML. It records the provider label, market `as_of_date`, export timestamp, data-quality warnings, evidence, changes, peer context, and a SHA-256 fingerprint of normalised history.

The snapshot has a deterministic `snapshot_id`: its canonical research content is hashed without the export timestamp, so the same inputs create the same identifier. The files do not include raw OHLCV rows, do not write to a server, and do not create public links. They preserve provenance and limitations; a snapshot does not predict price direction, recommend a trade, or claim investment performance.
