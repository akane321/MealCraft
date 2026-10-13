// The date the server plans from (Singapore, or a simulated day); set at start by plugins/server-today.ts.
let serverToday: string | null = null;
export function setServerToday(value: string | null): void {
  serverToday = value;
}

export function todayIsoDate(now?: Date): string {
  if (!now && serverToday) return serverToday;
  const at = now ?? new Date();
  const local = new Date(at.getTime() - at.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/** Format a plan's `YYYY-MM-DD` date. Read as UTC so no timezone shifts the day. */
export function formatPlanDate(
  value: string,
  options: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" },
): string {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString("en-SG", { ...options, timeZone: "UTC" });
}
