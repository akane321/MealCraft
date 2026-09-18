export function todayIsoDate(now = new Date()): string {
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

/** Format a plan's `YYYY-MM-DD` date. Read as UTC so no timezone shifts the day. */
export function formatPlanDate(
  value: string,
  options: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" },
): string {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString("en-SG", { ...options, timeZone: "UTC" });
}
