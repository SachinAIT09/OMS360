/* Shared pieces for asset age and health: condition colours and badges, asset links, the asset table and the labels that keep
   predicted, calculated and confirmed information apart. */
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Anchor, Badge, Card, Group, Progress, Table, Text, Tooltip } from "@mantine/core";
import { IconAlertTriangle, IconFlask, IconInfoCircle } from "@tabler/icons-react";
import type { Asset, AssetKind, Condition } from "../api/types";
import { fmt, money, pct } from "../lib/format";

export const CONDITIONS: Condition[] = ["Good", "Fair", "Poor", "Critical", "Unknown"];
export const BAND_COLOR: Record<Condition, string> = { Good: "teal", Fair: "yellow", Poor: "orange", Critical: "red", Unknown: "gray" };
/** Health-index colour scale (0 end of life … 100 as new), shared by maps and tables; grey when unknown. */
export const hiColor = (hi: number | null | undefined) =>
  hi == null ? "#8a9aa5" : hi >= 70 ? "#3ec46d" : hi >= 55 ? "#f5a623" : hi >= 40 ? "#f07a2e" : "#e0506a";
export const CONDITION_HEX: Record<Condition, string> = { Good: "#3ec46d", Fair: "#f5a623", Poor: "#f07a2e", Critical: "#e0506a", Unknown: "#8a9aa5" };

export const KIND_LABEL: Record<AssetKind, string> = {
  power_transformer: "Substation transformer", dist_transformer: "Distribution transformer", breaker: "Feeder breaker", recloser: "Recloser", pole: "Pole",
};
export const KIND_PLURAL: Record<AssetKind, string> = {
  power_transformer: "Substation transformers", dist_transformer: "Distribution transformers", breaker: "Feeder breakers", recloser: "Reclosers", pole: "Poles",
};

export function HealthBadge({ hi, condition, size = "sm" }: { hi: number | null; condition: Condition; size?: "xs" | "sm" | "md" }) {
  if (hi == null || condition === "Unknown") {
    return <Tooltip label="Not scored: the install year is not recorded"><Badge size={size} variant="light" color="gray" style={{ textTransform: "none" }}>Unknown</Badge></Tooltip>;
  }
  return <Badge size={size} variant="light" color={BAND_COLOR[condition]} style={{ textTransform: "none" }}>HI {Math.round(hi)} · {condition}</Badge>;
}

export function ConfidenceBadge({ value }: { value: "high" | "medium" | "low" }) {
  const label = { high: "High confidence — recent inspection and tests on file", medium: "Medium confidence — some evidence missing or old",
    low: "Low confidence — age or inspection not recorded" }[value];
  return <Tooltip label={label}><Badge size="xs" variant="outline" color={value === "high" ? "teal" : value === "medium" ? "yellow" : "gray"}>{value} confidence</Badge></Tooltip>;
}

export function StatusBadge({ status }: { status: string }) {
  return status === "damaged"
    ? <Tooltip label="Confirmed by a field assessment on an outage ticket"><Badge size="sm" color="red" leftSection={<IconAlertTriangle size={11} />}>Storm damage confirmed</Badge></Tooltip>
    : null;
}

export function AssetLink({ id, children }: { id: string; children?: ReactNode }) {
  return <Anchor component={Link} to={`/asset/${encodeURIComponent(id)}`} ff="monospace" fz="sm" onClick={e => e.stopPropagation()}>{children ?? id}</Anchor>;
}

/** Age with the year it is measured from and the reference date, so it can be checked. */
export function AgeText({ a }: { a: Pick<Asset, "install_year" | "age" | "age_reference"> }) {
  if (a.age == null) return <Text size="sm" c="dimmed">Not recorded</Text>;
  return (
    <Tooltip label={`Installed ${a.install_year}; age in whole years as of ${a.age_reference}`}>
      <Text size="sm" span>{a.age} y <Text span size="xs" c="dimmed">({a.install_year})</Text></Text>
    </Tooltip>
  );
}

/** Share of each condition band as one stacked bar. */
export function BandBar({ bands }: { bands: Partial<Record<Condition, number>> }) {
  const total = CONDITIONS.reduce((s, b) => s + (bands[b] ?? 0), 0) || 1;
  return (
    <>
      <Progress.Root size={14}>
        {CONDITIONS.filter(b => bands[b]).map(b => (
          <Tooltip key={b} label={`${b}: ${fmt(bands[b])} (${pct((bands[b] ?? 0) / total)})`}>
            <Progress.Section value={((bands[b] ?? 0) / total) * 100} color={BAND_COLOR[b]} />
          </Tooltip>))}
      </Progress.Root>
      <Group gap="md" mt={6}>{CONDITIONS.filter(b => bands[b]).map(b => (
        <Text key={b} size="xs" c="dimmed"><Text span c={`${BAND_COLOR[b]}.5`} fw={700}>■</Text> {b} {pct((bands[b] ?? 0) / total)}</Text>))}</Group>
    </>
  );
}

/** States what the health score is (and is not), wherever it is shown prominently. */
export function ModelNote({ compact }: { compact?: boolean }) {
  const text = "Health index, failure probability and risk come from an illustrative model, pending validation by the utility's asset engineers. "
    + "Missing install years show as Unknown and are not scored. Storm exposure is a prediction; damage is confirmed only by field assessments.";
  if (compact) return <Tooltip label={text} multiline w={360}><Badge variant="light" color="gray" leftSection={<IconFlask size={11} />} style={{ textTransform: "none" }}>Illustrative model</Badge></Tooltip>;
  return <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} p="xs"><Text size="xs">{text}</Text></Alert>;
}

/** A sortable-by-the-server list of units; every row opens the unit's record. */
export function AssetTable({ rows, title, showWhere, empty = "No units" }: { rows: Asset[]; title?: ReactNode; showWhere?: boolean; empty?: string }) {
  const go = useNavigate();
  return (
    <Card padding={0}>
      {title && <Text fw={600} p="md" pb={0}>{title}</Text>}
      {!rows.length ? <Text c="dimmed" size="sm" p="md">{empty}</Text> : (
        <Table.ScrollContainer minWidth={900}>
          <Table mt="xs" highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>Unit</Table.Th>{showWhere && <Table.Th>Where</Table.Th>}<Table.Th>Age</Table.Th><Table.Th ta="right">Rating</Table.Th>
              <Table.Th ta="right">Inspection</Table.Th><Table.Th>Health</Table.Th><Table.Th ta="right">Failure / yr</Table.Th>
              <Table.Th>What drives it</Table.Th><Table.Th ta="right">Replace</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map(a => (
              <Table.Tr key={a.id} className="row-click" onClick={() => go(`/asset/${encodeURIComponent(a.id)}`)}>
                <Table.Td><Text size="sm" fw={600}>{a.name}</Text><Group gap={4}><AssetLink id={a.id} />{a.status === "damaged" && <Badge size="xs" color="red">damaged</Badge>}</Group></Table.Td>
                {showWhere && <Table.Td><Text size="sm">{a.feeder_id ?? a.substation_id}</Text><Text size="xs" c="dimmed">{KIND_LABEL[a.kind]}</Text></Table.Td>}
                <Table.Td><AgeText a={a} /></Table.Td>
                <Table.Td ta="right" className="tabular">{rating(a)}</Table.Td>
                <Table.Td ta="right" className="tabular">{a.inspection_score ? `${a.inspection_score}/5` : <Text span c="dimmed" size="xs">none</Text>}
                  <Text size="xs" c="dimmed">{a.last_inspection ?? ""}</Text></Table.Td>
                <Table.Td><HealthBadge hi={a.health_index} condition={a.condition} /></Table.Td>
                <Table.Td ta="right" className="tabular">{pct(a.pof_12m, 1)}{a.health_index == null && <Text size="xs" c="dimmed">estimated</Text>}</Table.Td>
                <Table.Td><Text size="xs" c="dimmed">{a.drivers.slice(0, 2).join(" · ") || (a.gaps[0] ?? "—")}</Text></Table.Td>
                <Table.Td ta="right" className="tabular">{money(a.replacement_cost)}</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Card>
  );
}

export function rating(a: Pick<Asset, "kind" | "rating_kva" | "details">) {
  if (a.kind === "power_transformer") return `${(a.rating_kva / 1000).toFixed(1)} MVA`;
  if (a.kind === "dist_transformer") return `${a.rating_kva} kVA`;
  if (a.kind === "pole") return `${a.details.material ?? "wood"} · ${a.details.height_ft ?? "—"} ft`;
  return a.details.interrupter ?? "—";
}
