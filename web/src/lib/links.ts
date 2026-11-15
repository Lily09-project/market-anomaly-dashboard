/** Only http(s) URLs from data files become links; anything else (e.g. `javascript:`) is shown as text. */
export function safeExternalUrl(url: string): string | null {
  try {
    const { protocol } = new URL(url);
    return protocol === "https:" || protocol === "http:" ? url : null;
  } catch {
    return null;
  }
}
