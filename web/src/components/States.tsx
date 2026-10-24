import type { ReactNode } from "react";
import type { DatasetState } from "../app/hooks";

export function Loading({ label = "資料載入中" }: { label?: string }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}…
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="state state-error" role="alert">
      <strong>無法顯示這個頁面</strong>
      <p>{error.message}</p>
      <p className="muted">請重新整理；若問題持續，代表部署的資料檔不完整，網站不會用不完整的資料計算。</p>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

/** Render children only once every dataset is ready; otherwise show state. */
export function Gate<T extends unknown[]>({
  states,
  children,
}: {
  states: { [K in keyof T]: DatasetState<T[K]> };
  children: (...data: T) => ReactNode;
}) {
  const failed = states.find((s) => s.status === "error");
  if (failed && failed.status === "error") return <ErrorState error={failed.error} />;
  if (states.some((s) => s.status === "loading")) return <Loading />;
  const data = states.map((s) => (s.status === "ready" ? s.data : undefined)) as T;
  return <>{children(...data)}</>;
}
