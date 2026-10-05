import { Badge, type BadgeProps } from "@mantine/core";
import { label } from "../lib/format";

const EVENT: Record<string, string> = { monitoring: "gray", preparing: "yellow", active: "red", restoring: "blue", closed: "dark" };
const OUTAGE: Record<string, string> = { reported: "red", assessed: "orange", assigned: "yellow", in_progress: "blue", restored: "teal", cancelled: "gray" };
const PRIORITY: Record<string, string> = { critical: "red", high: "orange", normal: "gray", Critical: "red", High: "orange", Medium: "gray" };
const CREW: Record<string, string> = { available: "teal", staged: "cyan", assigned: "yellow", working: "blue", off_shift: "gray", released: "dark" };
const MESSAGE: Record<string, string> = { draft: "gray", pending: "yellow", scheduled: "cyan", sent: "teal", rejected: "red" };
const MA: Record<string, string> = { requested: "gray", confirmed: "yellow", en_route: "cyan", arrived: "teal", released: "dark", cancelled: "red" };

const make = (map: Record<string, string>) => ({ status, ...p }: { status: string } & BadgeProps) =>
  <Badge color={map[status] ?? "gray"} {...p}>{label(status)}</Badge>;

export const EventStatusBadge = make(EVENT);
export const OutageStatusBadge = make(OUTAGE);
export const CrewStatusBadge = make(CREW);
export const MessageStatusBadge = make(MESSAGE);
export const MutualAidBadge = make(MA);
export const PriorityBadge = ({ priority, ...p }: { priority: string } & BadgeProps) =>
  <Badge color={PRIORITY[priority] ?? "gray"} variant={priority.toLowerCase() === "critical" ? "filled" : "light"} {...p}>{label(priority)}</Badge>;
