/* Small shared visual pieces (Tailwind-styled) used across legends and tables. */
import type { ReactNode } from "react";

/** A colour sample for a legend: square, round dot, or a short line (for route colours). */
export function Swatch({ color, shape = "square", className = "" }: { color: string; shape?: "square" | "dot" | "line"; className?: string }) {
  const size = shape === "line" ? "h-[3px] w-3.5" : shape === "dot" ? "size-2.5 rounded-full" : "size-2.5 rounded-sm";
  return <span aria-hidden className={`inline-block shrink-0 ${size} ${className}`} style={{ background: color }} />;
}

/** One legend entry: swatch + label. */
export function LegendItem({ color, label, shape }: { color: string; label: ReactNode; shape?: "square" | "dot" | "line" }) {
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap text-xs text-dimmed">
      <Swatch color={color} shape={shape} />{label}
    </span>
  );
}

/** A thin horizontal bar: `value` is 0–100 % of the track. */
export function MiniBar({ value, color, dim = false, className = "w-[70px]" }: { value: number; color: string; dim?: boolean; className?: string }) {
  return (
    <span className={`relative inline-block h-1.5 shrink-0 overflow-hidden rounded-full bg-line ${className}`}>
      <span className={`absolute inset-y-0 left-0 rounded-full ${dim ? "opacity-[.45]" : ""}`} style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
    </span>
  );
}
