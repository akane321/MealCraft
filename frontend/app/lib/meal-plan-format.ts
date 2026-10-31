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

/** A plan's dates: one date for a one-day plan, else "29 Oct – 4 Nov". */
export function planRange(start: string, end: string): string {
  const fmt = (value: string) => formatPlanDate(value, { day: "numeric", month: "short" });
  return start === end ? fmt(start) : `${fmt(start)} – ${fmt(end)}`;
}

export const daysLabel = (count: number) => `${count} ${count === 1 ? "day" : "days"}`;

/**
 * The words that depend on how long a plan is: only a seven-day plan is "a week" (its budget is a week's);
 * a shorter or longer one is "this plan", and its budget is the plan's total. No length yet reads as a week.
 */
export function planLabels(dayCount?: number | null): { isWeek: boolean; noun: string; Noun: string; budgetSuffix: string; budgetName: string } {
  const isWeek = (dayCount ?? 7) === 7;
  return {
    isWeek,
    noun: isWeek ? "week" : "plan",
    Noun: isWeek ? "Week" : "Plan",
    budgetSuffix: isWeek ? "a week" : "for this plan",
    budgetName: isWeek ? "weekly budget" : "plan budget",
  };
}

/** A plan day's weekday, with its date number too once a plan runs past seven days (a weekday would then repeat). */
export function planDayName(value: string, weekday: "short" | "long", numbered = false): string {
  return formatPlanDate(value, numbered ? { weekday, day: "numeric" } : { weekday });
}

/**
 * A plan day as a sentence names it. The assistant reads a bare weekday as the plan's first such day, so past seven
 * days (a weekday repeats) the date is said too, in the "22 Oct" form it reads.
 */
export function sentenceDay(value: string, numbered = false): string {
  return numbered ? formatPlanDate(value, { weekday: "long", day: "numeric", month: "short" }).replace(",", "") : formatPlanDate(value, { weekday: "long" });
}
