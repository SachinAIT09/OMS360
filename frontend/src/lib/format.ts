import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(relativeTime);
dayjs.extend(utc);
dayjs.extend(timezone);

/** Operations run on the utility's local time (set from the territory profile at startup). */
export let TZ = "America/Chicago";
export const setTimeZone = (tz: string) => { TZ = tz; };
const local = (iso: string) => dayjs(iso).tz(TZ);

export const fmt = (n: number | null | undefined) => (n == null ? "—" : Math.round(n).toLocaleString("en-US"));
export const pct = (n: number | null | undefined, d = 0) => (n == null ? "—" : `${(n * 100).toFixed(d)}%`);
export const dt = (iso: string | null | undefined) => (iso ? local(iso).format("ddd MMM D, h:mm A") : "—");
export const dtShort = (iso: string | null | undefined) => (iso ? local(iso).format("ddd h:mm A") : "—");
export const date = (iso: string | null | undefined) => (iso ? local(iso).format("MMM D, YYYY") : "—");
export const time = (iso: string | null | undefined) => (iso ? local(iso).format("h:mm A") : "—");
export const ago = (iso: string | null | undefined) => (iso ? dayjs(iso).fromNow() : "—");
export const hoursUntil = (iso: string | null | undefined) => (iso ? dayjs(iso).diff(dayjs(), "hour", true) : null);
export const money = (n: number) => (n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : `$${fmt(n)}`);
export const label = (s: string) => s.replace(/_/g, " ").replace(/^./, c => c.toUpperCase());

/** Rain events are described by rainfall and rain onset; tornadoes by EF rating, damage paths and touchdown; the rest by
    category, wind and landfall. */
type EventLike = { kind: string; category: number; max_wind_mph: number; rain_total_in?: number | null; rain_rate_in_hr?: number | null };
export const isRain = (e: { kind: string } | null | undefined) => e?.kind === "Rain Event";
export const isTornado = (e: { kind: string } | null | undefined) => e?.kind === "Tornado";
/** "EF4" for tornadoes, "Cat 3" otherwise. */
export const scale = (e: { kind: string } | null | undefined, c: number) => (isTornado(e) ? `EF${c}` : `Cat ${c}`);
export const intensity = (e: EventLike) =>
  isRain(e) ? `${e.rain_total_in ?? "—"} in rain · ${e.rain_rate_in_hr ?? "—"} in/hr peak` : `${scale(e, e.category)} · ${e.max_wind_mph} mph`;
/** "landfall", "touchdown" or "rain onset": the moment predicted restoration hours count from. */
export const impactWord = (e: { kind: string } | null | undefined) => (isRain(e) ? "rain onset" : isTornado(e) ? "touchdown" : "landfall");
export const scenario = (p: { scenario?: string; category: number; kind?: string }) => p.scenario ?? (p.kind === "tornado" ? `EF${p.category}` : `Cat ${p.category}`);

/** Outage-severity colour scale shared by maps, tables and meters. */
export const sevColor = (v: number) => (v < 0.08 ? "#3ec46d" : v < 0.2 ? "#f5a623" : v < 0.4 ? "#f07a2e" : "#e0506a");

export const FAC_COLOR: Record<string, string> = { H: "#e0506a", W: "#2b9bff", E: "#f5a623", S: "#3ec46d", M: "#c3b1ff" };

export { dayjs };
