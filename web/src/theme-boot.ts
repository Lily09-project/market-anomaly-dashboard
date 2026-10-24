// Apply a saved theme before React renders to avoid a flash of the wrong
// colours. Kept as a separate module because the CSP forbids inline scripts.
try {
  const saved = window.localStorage.getItem("market-regime-lab-theme");
  if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
} catch {
  // Storage unavailable: fall back to the OS preference.
}
