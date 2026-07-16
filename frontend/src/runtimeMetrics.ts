export function formatCostUsd(value: number | null | undefined): string {
  if (value == null) return "Unknown";
  if (value === 0) return "$0.0000";
  if (value > 0 && value < 0.0001) return "<$0.0001";
  return `$${value.toFixed(4)}`;
}
