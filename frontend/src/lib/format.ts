import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import timezone from "dayjs/plugin/timezone";

dayjs.extend(relativeTime);
dayjs.extend(utc);
dayjs.extend(timezone);

/** Operations run on the utility's local time. */
export const TZ = "America/New_York";
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

/** Outage-severity colour scale shared by maps, tables and meters. */
export const sevColor = (v: number) => (v < 0.08 ? "#3ec46d" : v < 0.2 ? "#f5a623" : v < 0.4 ? "#f07a2e" : "#e0506a");

export const FAC_COLOR: Record<string, string> = { H: "#e0506a", W: "#2b9bff", E: "#f5a623", S: "#3ec46d", M: "#c3b1ff" };

export { dayjs };
