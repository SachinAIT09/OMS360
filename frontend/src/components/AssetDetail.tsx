/* One unit's full record: identity and hierarchy, age (with its source and reference date), health with the evidence behind
   it and what is missing, history, predicted storm exposure (kept apart from confirmed damage), recommendations and work orders. */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Alert, Anchor, Badge, Breadcrumbs, Button, Card, Grid, Group, List, Modal, NumberInput, Select, SimpleGrid, Stack, Table, Text, TextInput, Timeline, Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconAlertTriangle, IconCircleCheck, IconClipboardList, IconTornado } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet } from "../api/hooks";
import type { AssetDetail as Detail, AssetRecommendation, WorkOrder } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { date, dt, fmt, label, money, pct } from "../lib/format";
import { PROFILE } from "../lib/profile";
import { AgeText, ConfidenceBadge, HealthBadge, KIND_LABEL, ModelNote, StatusBadge, hiColor, rating } from "./assetUi";
import { ErrorState, Loading, Stat } from "./common";
import { TerritoryMap } from "./TerritoryMap";

const PRIORITY_COLOR: Record<string, string> = { Critical: "red", High: "orange", Medium: "yellow", Low: "gray" };
const HISTORY_COLOR: Record<string, string> = { damage: "red", failure: "red", replacement: "teal", repair: "teal", inspection: "blue", test: "grape", maintenance: "cyan" };

export function AssetDetailView({ id, compact }: { id: string; compact?: boolean }) {
  const { data: a, error } = useGet<Detail>(`/assets/item/${encodeURIComponent(id)}`);
  const { can } = useAuth();
  const [woOpen, woCtl] = useDisclosure(false);
  const [preset, setPreset] = useState<AssetRecommendation | null>(null);
  if (error) return <ErrorState error={error} />;
  if (!a) return <Loading />;
  const p = a.parents;
  const d = a.details;
  const inputs: [string, string][] = [
    ["Manufacturer", a.manufacturer || "—"], ["Rating", rating(a)], ["Mounting", label(a.mounting)],
    ["Last inspection", a.last_inspection ? `${a.last_inspection}${a.inspection_score ? ` · score ${a.inspection_score}/5` : ""}` : "None on file"],
    ...(a.peak_load_pct != null && (a.kind === "dist_transformer" || a.kind === "power_transformer") ? [["Peak load", `${Math.round(a.peak_load_pct)}% of nameplate`] as [string, string]] : []),
    ...(a.kind === "power_transformer" ? [["Dissolved gas (TDCG)", a.dga_tdcg_ppm != null ? `${fmt(a.dga_tdcg_ppm)} ppm` : "No test on file"],
      ["Oil moisture", a.oil_moisture_ppm != null ? `${a.oil_moisture_ppm} ppm` : "—"], ["Through-faults", `${a.through_faults ?? "—"}`],
      ["Tap changer", a.ltc ? "Yes" : "No"], ["Maintenance", a.maintenance_overdue ? "Overdue" : "Up to date"]] as [string, string][] : []),
    ...(a.kind === "pole" ? [["Material", d.material ?? "—"], ["Height", d.height_ft ? `${d.height_ft} ft` : "—"],
      ["Remaining strength", d.strength_pct != null ? `${d.strength_pct}% (${d.strength_test_year})` : "No ground-line test on file"]] as [string, string][] : []),
    ...(a.kind === "breaker" || a.kind === "recloser" ? [["Interrupter", d.interrupter ?? "—"],
      ["Operations", d.operations != null ? `${fmt(d.operations)} of ${fmt(d.rated_operations)} rated` : "—"],
      ["Last test", d.test_result ? `${d.test_result} (${d.last_test_year})` : "No test on file"]] as [string, string][] : []),
  ];
  const confirmed = a.history.filter(h => h.kind === "damage");
  return (
    <Stack gap="md">
      <Breadcrumbs separator="›" fz="sm">
        <Anchor component={Link} to="/network">{PROFILE.state || "Territory"}</Anchor>
        {p.region_id && <Anchor component={Link} to={`/network?region=${p.region_id}`}>{p.region}</Anchor>}
        {p.substation_id && <Anchor component={Link} to={`/network?region=${p.region_id ?? ""}&sub=${p.substation_id}`}>{p.substation}</Anchor>}
        {p.circuit_id && <Anchor component={Link} to={`/network?region=${p.region_id ?? ""}&sub=${p.substation_id ?? ""}&circuit=${p.circuit_id}`}>{p.circuit_id}</Anchor>}
        <Text size="sm" ff="monospace">{a.id}</Text>
      </Breadcrumbs>
      <Group justify="space-between" align="flex-start" wrap="wrap">
        <div>
          {!compact && <Title order={2} fz={24}>{a.name}</Title>}
          {compact && <Text fw={700}>{a.name}</Text>}
          <Group gap={6} mt={4}>
            <Badge variant="light">{KIND_LABEL[a.kind]}</Badge><HealthBadge hi={a.health_index} condition={a.condition} /><ConfidenceBadge value={a.confidence} />
            <StatusBadge status={a.status} />
            <Badge size="xs" variant="outline" color={a.source === "imported" ? "teal" : "gray"}>{a.source === "imported" ? "Imported record" : "Sandbox record (synthetic)"}</Badge>
          </Group>
        </div>
        {can("workorders.manage") && <Button size="xs" leftSection={<IconClipboardList size={14} />} onClick={() => { setPreset(null); woCtl.open(); }}>New work order</Button>}
      </Group>

      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <Stat label="Age" value={a.age != null ? `${a.age} y` : "Unknown"} hint={a.install_year ? `installed ${a.install_year} · as of ${date(a.age_reference)}` : "install year not recorded"} />
        <Stat label="Health index" value={a.health_index != null ? Math.round(a.health_index) : "—"} color={a.health_index != null ? (a.health_index >= 70 ? "teal" : a.health_index >= 50 ? "yellow" : "red") : undefined}
          hint={a.condition === "Unknown" ? "not scored" : `${a.condition} · illustrative model`} />
        <Stat label="Failure / 12 mo" value={pct(a.pof_12m, 1)} hint={a.health_index == null ? "estimated from a typical age" : "Weibull on effective age"} />
        <Stat label="Replacement" value={money(a.replacement_cost)} hint={`risk ${a.risk_score.toFixed(2)} customer-outages / yr`} />
      </SimpleGrid>

      {a.status === "damaged" && <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Storm damage confirmed">
        {confirmed[0]?.summary ?? "Confirmed by a field assessment."} Source: field assessment on the outage ticket.</Alert>}

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: compact ? 12 : 6 }}>
          <Card withBorder>
            <Text fw={600} mb="xs">Why this health index</Text>
            {a.drivers.length ? <List size="sm" spacing={4}>{a.drivers.map(x => <List.Item key={x}>{x}</List.Item>)}</List>
              : <Text size="sm" c="dimmed">No significant penalties.</Text>}
            {a.gaps.length > 0 && <>
              <Text fw={600} size="sm" mt="sm" c="yellow.6">Missing or stale information</Text>
              <List size="sm" spacing={2}>{a.gaps.map(g => <List.Item key={g}>{g}</List.Item>)}</List>
            </>}
            <Table fz="sm" mt="sm" verticalSpacing={4}><Table.Tbody>
              <Table.Tr><Table.Td c="dimmed">Install year</Table.Td><Table.Td ta="right">{a.install_year ?? "Not recorded"}</Table.Td></Table.Tr>
              <Table.Tr><Table.Td c="dimmed">Age</Table.Td><Table.Td ta="right"><AgeText a={a} /></Table.Td></Table.Tr>
              {inputs.map(([k, v]) => <Table.Tr key={k}><Table.Td c="dimmed">{k}</Table.Td><Table.Td ta="right">{v}</Table.Td></Table.Tr>)}
            </Table.Tbody></Table>
            <ModelNote compact />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: compact ? 12 : 6 }}>
          <Stack gap="md">
            <Card withBorder>
              <Text fw={600} mb="xs">Storm exposure <Badge size="xs" variant="light" color="gray" ml={4}>prediction</Badge></Text>
              {!a.exposure.length ? <Text size="sm" c="dimmed">No open storm event has a prediction for this unit's circuit.</Text> :
                a.exposure.map(x => (
                  <Alert key={x.event_id} p="xs" mb={6} color={x.in_path ? "orange" : "gray"} icon={x.in_path ? <IconTornado size={16} /> : undefined}>
                    <Text size="sm"><b>{x.event}</b> — circuit {x.circuit}: {x.in_path ? `in the predicted EF${x.path_ef} damage path` : x.path_km != null ? `${x.path_km} km from the nearest path` : "affected area"};
                      {" "}{pct(x.pct)} of customers predicted out, back in ~{Math.round(x.eta_h)} h.</Text>
                    <Text size="xs" c="dimmed">{x.basis}.</Text>
                  </Alert>))}
            </Card>
            <Card withBorder>
              <Text fw={600} mb="xs">Recommended actions</Text>
              {!a.recommendations.length ? <Text size="sm" c="dimmed">None.</Text> : (
                <Stack gap={6}>{a.recommendations.map(r => (
                  <Group key={r.key} justify="space-between" wrap="nowrap" align="flex-start">
                    <div><Group gap={6}><Badge size="xs" color={PRIORITY_COLOR[r.priority]}>{r.priority}</Badge><Text size="sm" fw={600}>{r.title}</Text></Group>
                      <Text size="xs" c="dimmed">{r.reason}</Text></div>
                    {can("workorders.manage") && <Button size="compact-xs" variant="light" onClick={() => { setPreset(r); woCtl.open(); }}>Work order</Button>}
                  </Group>))}</Stack>)}
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: compact ? 12 : 7 }}>
          <Card withBorder>
            <Text fw={600} mb="sm">History</Text>
            {!a.history.length ? <Text size="sm" c="dimmed">No inspection, test or event history on file.</Text> : (
              <Timeline bulletSize={12} lineWidth={2}>
                {a.history.map((h, i) => (
                  <Timeline.Item key={h.id ?? `r${i}`} color={HISTORY_COLOR[h.kind] ?? "gray"} title={<Text size="sm" fw={500}>{h.summary}</Text>}>
                    <Text size="xs" c="dimmed">{date(h.at)} · {label(h.kind)} · {h.source}</Text>
                  </Timeline.Item>))}
              </Timeline>)}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: compact ? 12 : 5 }}>
          <Stack gap="md">
            <WorkOrders rows={a.work_orders} />
            <Card withBorder>
              <Text fw={600} mb="xs">Outages</Text>
              {!a.outages.length ? <Text size="sm" c="dimmed">None linked to this unit or open on its circuit.</Text> : (
                <Table fz="xs"><Table.Tbody>{a.outages.map(o => (
                  <Table.Tr key={o.id}><Table.Td><Anchor component={Link} to={`/outages?open=${o.id}`} fz="xs">{o.number}</Anchor>
                    {o.this_unit && <Badge size="xs" ml={4} color="red" variant="light">this unit</Badge>}</Table.Td>
                    <Table.Td>{o.event ?? "—"}</Table.Td><Table.Td>{label(o.status)}</Table.Td><Table.Td>{o.damage} · {o.cause}</Table.Td>
                    <Table.Td ta="right">{fmt(o.customers)}</Table.Td></Table.Tr>))}</Table.Tbody></Table>)}
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>

      {!compact && (
        <Card padding="sm" withBorder>
          <Text fw={600} mb="xs">Location</Text>
          <TerritoryMap height={260} center={[a.lat, a.lng]} zoom={14} pins={[{ id: a.id, lat: a.lat, lng: a.lng, color: hiColor(a.health_index), popup: <b>{a.id}</b> }]} />
          {a.critical_facilities.length > 0 && <Text size="xs" c="dimmed" mt={6}>Critical facilities on this circuit: {a.critical_facilities.join(", ")}</Text>}
        </Card>)}
      <WorkOrderModal opened={woOpen} onClose={woCtl.close} assetId={a.id} preset={preset} />
    </Stack>
  );
}

const WO_STATUS = ["open", "scheduled", "done", "cancelled"];

export function WorkOrders({ rows, showAsset }: { rows: WorkOrder[]; showAsset?: boolean }) {
  const { can } = useAuth();
  const upd = useAction(({ id, status }: { id: number; status: string }) => api.patch(`/work-orders/${id}`, { status }), { success: "Work order updated", invalidate: ["/assets", "/work-orders"] });
  return (
    <Card withBorder padding={showAsset ? 0 : undefined}>
      <Text fw={600} mb="xs" p={showAsset ? "md" : 0} pb={0}>Work orders</Text>
      {!rows.length ? <Text size="sm" c="dimmed" p={showAsset ? "md" : 0}>None.</Text> : (
        <Table.ScrollContainer minWidth={showAsset ? 760 : 300}>
          <Table fz="sm" highlightOnHover>
            <Table.Tbody>{rows.map(w => (
              <Table.Tr key={w.id}>
                <Table.Td><Group gap={6}><Badge size="xs" color={PRIORITY_COLOR[w.priority]}>{w.priority}</Badge><Text size="sm" fw={500}>{w.title}</Text></Group>
                  <Text size="xs" c="dimmed">{w.reason}</Text>
                  <Text size="xs" c="dimmed">#{w.id} · {w.created_by} · {dt(w.created_at)}{w.due_at ? ` · due ${date(w.due_at)}` : ""}</Text></Table.Td>
                {showAsset && <Table.Td><Anchor component={Link} to={`/asset/${encodeURIComponent(w.asset_id)}`} ff="monospace" fz="sm">{w.asset_id}</Anchor>
                  <Text size="xs" c="dimmed">{w.asset_kind ? KIND_LABEL[w.asset_kind] : ""} · {w.feeder_id ?? w.substation_id}</Text></Table.Td>}
                <Table.Td w={150}>
                  {can("workorders.manage")
                    ? <Select size="xs" value={w.status} data={WO_STATUS.map(s => ({ value: s, label: label(s) }))} allowDeselect={false}
                        onChange={v => v && v !== w.status && upd.mutate({ id: w.id, status: v })} aria-label={`Status of work order ${w.id}`} />
                    : <Badge variant="light" color={w.status === "done" ? "teal" : "gray"}>{w.status}</Badge>}
                </Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>)}
    </Card>
  );
}

function WorkOrderModal({ opened, onClose, assetId, preset }: { opened: boolean; onClose: () => void; assetId: string; preset: AssetRecommendation | null }) {
  const [kind, setKind] = useState(preset?.kind ?? "inspect");
  const [title, setTitle] = useState(preset?.title ?? "");
  const [priority, setPriority] = useState(preset?.priority ?? "Medium");
  const [days, setDays] = useState<number | string>(30);
  const key = preset?.key ?? "none";
  const [seen, setSeen] = useState(key);
  if (seen !== key) {  // a different recommendation opened the modal: take its values
    setSeen(key); setKind(preset?.kind ?? "inspect"); setTitle(preset?.title ?? ""); setPriority(preset?.priority ?? "Medium");
  }
  const create = useAction(() => api.post(`/assets/item/${encodeURIComponent(assetId)}/work-orders`,
    { kind, title, priority, reason: preset?.reason ?? "", due_days: Number(days) || null }), { success: "Work order created", invalidate: ["/assets", "/work-orders"] });
  return (
    <Modal opened={opened} onClose={onClose} title={`New work order — ${assetId}`}>
      <Stack>
        <TextInput label="Title" value={title} onChange={e => setTitle(e.currentTarget.value)} placeholder="e.g. Inspect after the storm" data-autofocus />
        <Group grow>
          <Select label="Type" value={kind} onChange={v => v && setKind(v)} allowDeselect={false}
            data={["inspect", "test", "repair", "replace", "maintain"].map(k => ({ value: k, label: label(k) }))} />
          <Select label="Priority" value={priority} onChange={v => v && setPriority(v as typeof priority)} allowDeselect={false} data={["Critical", "High", "Medium", "Low"]} />
          <NumberInput label="Due in (days)" min={1} max={730} value={days} onChange={setDays} />
        </Group>
        {preset && <Text size="xs" c="dimmed">From the recommendation: {preset.reason}</Text>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button leftSection={<IconCircleCheck size={16} />} disabled={title.trim().length < 3} loading={create.isPending}
            onClick={async () => { await create.mutateAsync(); onClose(); }}>Create</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
