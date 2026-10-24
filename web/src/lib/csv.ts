/**
 * CSV export that is safe to open in spreadsheet software: cells that start
 * with a formula trigger (=, +, -, @), even behind whitespace or control
 * characters, are prefixed with an apostrophe so they are shown as text instead of being executed.
 */
const CONTROL_PREFIX = /^[\t\r\n\v\f]/;
const LEADING_SPACE = /^\s+/;

/**
 * Spreadsheets ignore leading whitespace and control characters before a
 * formula, so the check looks past them. A lone "-" is plain text.
 */
function looksLikeFormula(text: string): boolean {
  const trimmed = text.replace(LEADING_SPACE, "");
  if (/^[=+@]/.test(trimmed)) return true;
  if (trimmed.startsWith("-") && trimmed.length > 1) return true;
  return CONTROL_PREFIX.test(text) && trimmed.length > 0;
}

export function escapeCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value !== "number" && looksLikeFormula(text)) text = `'${text}`;
  if (/[",\n\r]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function toCsv(columns: readonly string[], rows: readonly Record<string, unknown>[]): string {
  const header = columns.map(escapeCell).join(",");
  const body = rows.map((row) => columns.map((c) => escapeCell(row[c])).join(","));
  // UTF-8 BOM so Excel opens Traditional Chinese correctly.
  return `\uFEFF${[header, ...body].join("\r\n")}\r\n`;
}

export function downloadText(filename: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
