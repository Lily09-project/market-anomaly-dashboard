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
- **Quote board.** The 全市場 table scrolls inside its own region with a pinned header row and code column, tabular figures in the numeric face, zebra rows and ▲/▼ glyphs drawn by CSS beside the signed value.
- **Type and rhythm.** One display size (`--step-4`), headings at `--step-3`/`--step-1`/`--step-0`, labels at `--label` (14px), figures in `--font-num` with tabular numerals; spacing only from `--space-1…8`. Charts declare their pixel height so measuring the width never moves the page.

## Adopted rules: typography, spacing, hairlines, depth (2026-11)

參考 awesome-design-md（MIT）的 Binance DESIGN.md 版面與字體規則，配色維持本站。 Only non-colour technique was taken; the reference's colours, fonts, logo and wording are not used. Kraken's DESIGN.md (same collection) was read as a second opinion on shadow restraint only.

- **Numeric face.** The reference pairs an editorial face with a separate face for figures. Here `--font-num` is a system sans stack with tabular, lining numerals (Segoe UI / SF / Roboto, CJK fallbacks for units). Every price, percentage, count, date and axis label uses it; `--font-mono` is kept only for hashes, file names and code. No font files are downloaded.
- **Weights.** Four steps only: `--weight-regular` 400 body, `--weight-medium` 500 table figures and nav links, `--weight-semibold` 600 titles, labels and buttons, `--weight-bold` 700 display and stat figures. Display is never softened below 700.
- **Tracking and leading.** Display `--track-display` (−0.02em) at `--lh-display` 1.12; titles at 0 tracking and `--lh-title` 1.3; labels `--track-label` (0.02em). Body stays at 1.65 because Chinese running text needs more leading than the reference's 1.5.
- **Spacing and grid.** 4px base. Desktop rhythm: 32px (`--space-6`) between page bands, 24px (`--space-5`) gutters between analysis panels, 16px between dense rail items and table rows. The 8/4 chart + rail split is unchanged.
- **Hairlines.** Borders are `--hairline` (1px `--line`) or `--hairline-strong` for table heads and controls, nothing heavier. Cards drop their outline (a transparent border stays for forced-colours mode).
- **Depth.** Flat: the canvas → `--bg-raised` step is the elevation. Removed the card gradient, the sticky-toolbar shadow, the header glass blur, the price-line glow and the logo-mark gradient. No atmospheric gradients.
- **Radius scale.** `--radius-xs` 2px marks and meter cells, `--radius-s` 4px chips and tags, `--radius-m` 6px buttons and inputs, `--radius-l` 8px cards, `--radius-xl` 12px for the quote-board and market-breadth containers. No pills.
- **Controls.** `--control-h` is 44px for touch and 40px from 1024px. Buttons: 14px / 600 label, 24px side padding, 6px radius; inputs, selects and segmented tabs share the same height.
- **Top nav.** 64px (`--header-h`), solid canvas with one hairline, 14px / 500 links, the current page in the accent at 600 with a 2px underline.
- **Trading semantics.** `--up` / `--down` (Taiwan convention, red up and green down) mark price direction only, as text colour or a thin bar, always beside a drawn ▲/▼ so hue is never the only cue; they are never card fills. Pass / caution / fail use the status aliases `--success`, `--warn`, `--danger`, which point at the same existing colours but keep the two meanings apart in code.
- **Dense tables.** Right-aligned tabular figures in the numeric face at 500, 13–14px head labels at 500 in `--muted`, 8px row padding, a hairline between rows, a pinned header and code column. The quote board keeps its zebra rows (a deliberate departure from the reference) because it is wide enough that the eye needs a guide across eight columns.
- **Stat blocks.** A flat figure in the numeric face at 700 with a small label above and a muted note below; no box of its own. The cover's X/N figures remount when the data arrives, so the proportional numerals cause no layout shift.

