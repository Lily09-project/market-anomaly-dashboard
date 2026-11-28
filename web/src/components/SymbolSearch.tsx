import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { formatNumber, formatSignedPercent } from "../lib/format";
import { pushRecent, rankSymbols, readRecent, withRecentFirst, type SymbolOption } from "../lib/symbolSearch";
import { Icon } from "./Icon";
import "./SymbolSearch.css";

const isEditable = (target: EventTarget | null) =>
  target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

const signOf = (change: number | null | undefined) =>
  change === null || change === undefined ? undefined : Math.sign(Number((change * 100).toFixed(2)));

/**
 * Searchable symbol picker (WAI-ARIA combobox with a listbox popup), for lists
 * too long for a select: type a code or name, move with ↑↓, Enter picks, Esc
 * closes. With `shortcut`, "/" anywhere on the page focuses it.
 */
export function SymbolSearch({
  options,
  value,
  onChange,
  label,
  labelledBy,
  id,
  shortcut = false,
}: {
  options: SymbolOption[];
  value: string;
  onChange: (symbol: string) => void;
  /** Accessible name; ignored when labelledBy is given. */
  label?: string;
  labelledBy?: string;
  /** Lets an external <label htmlFor> name the input. */
  id?: string;
  shortcut?: boolean;
}) {
  const auto = useId();
  const inputId = id ?? `${auto}-input`;
  const listId = `${auto}-list`;
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const [active, setActive] = useState(0);
  const selected = options.find((o) => o.symbol === value);

  const rows = useMemo(
    () => (query.trim() ? rankSymbols(options, query).map((option) => ({ option, recent: false })) : withRecentFirst(options, recent)),
    [options, query, recent],
  );

  const openList = () => {
    const remembered = readRecent();
    setRecent(remembered);
    setQuery("");
    const start = withRecentFirst(options, remembered).findIndex((row) => row.option.symbol === value);
    setActive(Math.max(start, 0));
    setOpen(true);
  };

  const close = () => {
    setOpen(false);
    setQuery("");
  };

  const choose = (symbol: string) => {
    setRecent(pushRecent(symbol));
    close();
    if (symbol !== value) onChange(symbol);
  };

  // Keep the active option visible while moving through a long list.
  useEffect(() => {
    if (!open) return;
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open]);

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || isEditable(event.target)) return;
      event.preventDefault();
      input.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcut]);

  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) return openList();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (rows.length ? (i + step + rows.length) % rows.length : 0));
    } else if (event.key === "Enter") {
      if (!open) return;
      event.preventDefault();
      const row = rows[active];
      if (row) choose(row.option.symbol);
    } else if (event.key === "Escape") {
      if (!open) return;
      event.preventDefault();
      close();
    } else if (event.key === "PageDown" || event.key === "PageUp") {
      if (!open || !rows.length) return;
      event.preventDefault();
      const step = event.key === "PageDown" ? 8 : -8;
      setActive((i) => Math.min(Math.max(i + step, 0), rows.length - 1));
    }
  };

  const display = selected ? `${selected.symbol} ${selected.name}` : value;
  const activeId = open && rows[active] ? `${auto}-opt-${active}` : undefined;

  return (
    <div className="symbol-search" data-open={open || undefined}>
      <Icon name="search" size={16} className="symbol-search-icon" />
      <input
        ref={input}
        id={inputId}
        className="symbol-search-input"
        type="text"
        role="combobox"
        aria-label={labelledBy ? undefined : label}
        aria-labelledby={labelledBy}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        autoComplete="off"
        spellCheck={false}
        enterKeyHint="go"
        placeholder={open ? `${display} · 輸入代號或名稱` : display}
        value={open ? query : display}
        onFocus={(event) => {
          openList();
          event.currentTarget.select();
        }}
        onClick={() => !open && openList()}
        onBlur={close}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          if (!open) setOpen(true);
        }}
        onKeyDown={onKeyDown}
      />
      {shortcut && !open && (
        <kbd className="symbol-search-key" aria-hidden="true" title="按 / 搜尋標的">
          /
        </kbd>
      )}
      <ul
        ref={list}
        id={listId}
        className="symbol-search-list"
        role="listbox"
        aria-label={label ?? "標的"}
        hidden={!open}
        // Keep focus in the input so a click does not blur (and close) before it lands.
        onMouseDown={(event) => event.preventDefault()}
      >
        {open &&
          rows.map(({ option, recent: isRecent }, index) => {
            const sign = signOf(option.change);
            return (
              <li
                key={option.symbol}
                id={`${auto}-opt-${index}`}
                data-index={index}
                role="option"
                aria-label={[
                  `${option.symbol} ${option.name}`,
                  option.close !== undefined ? `收盤 ${formatNumber(option.close, 2)}，漲跌 ${formatSignedPercent(option.change ?? null, 2)}` : null,
                  isRecent ? "最近看過" : null,
                ].filter(Boolean).join("，")}
                aria-selected={option.symbol === value}
                data-active={index === active || undefined}
                data-control={option.isControl || undefined}
                onClick={() => choose(option.symbol)}
                onMouseMove={() => index !== active && setActive(index)}
              >
                <span className="symbol-search-code">{option.symbol}</span>
                <span className="symbol-search-name">
                  {option.name}
                  {isRecent && <span className="symbol-search-tag">最近</span>}
                </span>
                {option.close !== undefined && (
                  <span className="symbol-search-quote">
                    <span className="symbol-search-close">{formatNumber(option.close, 2)}</span>
                    <span className="symbol-search-change" data-sign={sign}>
                      {formatSignedPercent(option.change ?? null, 2)}
                    </span>
                  </span>
                )}
              </li>
            );
          })}
      </ul>
      {open && (
        <p className="symbol-search-status" role="status">
          {rows.length ? <span className="visually-hidden">{rows.length} 個符合的標的</span> : `找不到符合「${query.trim()}」的標的`}
        </p>
      )}
    </div>
  );
}

/** Above this many symbols a select becomes a chore to scroll; switch to search. */
export const SEARCH_THRESHOLD = 12;

/** Build search options (with the latest quote) from overview series. */
export function toSymbolOptions(symbols: { symbol: string; name: string; close: number[]; is_control?: boolean }[]): SymbolOption[] {
  return symbols.map((s) => {
    const last = s.close.at(-1);
    const prev = s.close.at(-2);
    return {
      symbol: s.symbol,
      name: s.name,
      close: last,
      change: last !== undefined && prev !== undefined && prev !== 0 ? last / prev - 1 : null,
      isControl: s.is_control,
    };
  });
}
