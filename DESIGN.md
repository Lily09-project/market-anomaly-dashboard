# market-anomaly-dashboard: interface design

Reference: [binance design analysis](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/binance/DESIGN.md), curated by VoltAgent. This is an independent adaptation; no affiliation, brand assets or proprietary fonts.

Single dark market workspace. Near-black canvas, gold actions, flat dense surfaces, price-direction colors, numeric typography and an 8/4 analysis split.

Use local system fonts, 16px body and 14px secondary text. Keep semantic data colors distinct from decorative accents. Preserve data labels, warnings, keyboard focus, chart tables, cancellation and existing route contracts. No external font or asset requests. Mobile controls retain at least 44px height. All pages reflow at 200% text; wide data tables scroll inside named keyboard-accessible regions.

The source collection is MIT licensed. Token and component adaptations retain its notice in THIRD_PARTY_DESIGN_NOTICES.txt.

## Layout direction: 研究報告 × 交易終端

The palette above is frozen; `web/src/styles/tokens.css` may only gain aliases of existing values (for example `--up: var(--bad)`, `--down: var(--good)` for the Taiwan red-up, green-down quote convention).

- **Overview as a report cover.** A rule line with the data cut-off, a static title that paints before any data file, the computed core finding with its X/N figures and a one-cell-per-symbol meter, a colophon (source, period, trading days, coverage) and a numbered contents list. Data-driven parts keep their size while loading, so nothing shifts.
- **One terminal toolbar.** `SymbolBar` is the single symbol (and, on the overview, period) control for the five analysis pages: a quote read-out, every symbol in one native radio group (arrow keys, screen-reader group label), URL state unchanged. Sticky under the header on desktop; a swipeable chip rail on phones.
- **Chart as hero, conclusions in a rail.** `.analysis` puts the rail (verdicts, read-outs, method notes) on the right from 1024px. DOM order is rail first, so screen readers meet the conclusion before the evidence; below 1024px the panels interleave by `.is-lead`, `.is-hero` and `.is-last`. Inner pairs size by container query, not window width.
- **Quote board.** The 全市場 table scrolls inside its own region with a pinned header row and code column, mono tabular figures, zebra rows and ▲/▼ glyphs drawn by CSS beside the signed value.
- **Type and rhythm.** One display size (`--step-4`), headings at `--step-3`/`--step-1`/`--step-0`, labels at `--label` (14px), figures in the mono stack with tabular numerals; spacing only from `--space-1…8`. Charts declare their pixel height so measuring the width never moves the page.
