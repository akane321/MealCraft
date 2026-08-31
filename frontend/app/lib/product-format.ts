export function formatSgd(value: number | null): string {
  return value === null ? "Unavailable" : `S$${value.toFixed(2)}`;
}

export function formatQuantity(value: number | null, unit: string | null): string {
  if (value === null) return "Quantity unavailable";
  return `${Number.isInteger(value) ? value : value.toFixed(1)} ${unit ?? "units"}`;
}
