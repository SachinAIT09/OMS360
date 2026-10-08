import { useState } from "react";
import { Badge, Button, Card, Group, NumberInput, Progress, Select, SimpleGrid, Switch, Table, Text, Tooltip } from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconWorldUpload } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet, useRoutes } from "../api/hooks";
import type { NetworkEtrs } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { dt, dtShort, fmt } from "../lib/format";
import { Empty, Loading } from "./common";
import { TerritoryMap } from "./TerritoryMap";

const confColor = (c: number, bar: number) => (c >= bar ? "teal" : c >= bar - 15 ? "yellow" : "orange");

function Confidence({ value, bar }: { value: number | null; bar: number }) {
  if (value == null) return <Text size="sm" c="dimmed">—</Text>;
  return (
    <Group gap={6} wrap="nowrap" justify="flex-end">
      <Progress value={value} color={confColor(value, bar)} size="sm" w={60} />
      <Text size="sm" fw={600} w={36} ta="right">{value}%</Text>
    </Group>
  );
}

/** ETRs by region (rollup) — the last circuit expected in each region, customer-weighted confidence. */
export function RegionEtrTable({ eventId, onPick }: { eventId: number; onPick: (region: string) => void }) {
  const { data } = useGet<NetworkEtrs>(`/events/${eventId}/etrs`, { refetchInterval: 30_000 });
  if (!data) return <Loading />;
  return (
    <Card padding={0}>
      <Table.ScrollContainer minWidth={850}>
        <Table>
          <Table.Thead><Table.Tr>
            <Table.Th>Region</Table.Th><Table.Th ta="right">Customers out</Table.Th><Table.Th ta="right">Circuits out</Table.Th><Table.Th ta="right">Open tickets</Table.Th>
            <Table.Th>Last circuit expected</Table.Th><Table.Th ta="right">Confidence</Table.Th><Table.Th ta="right">Circuits published</Table.Th>
          </Table.Tr></Table.Thead>
          <Table.Tbody>{data.regions.map(r => (
            <Table.Tr key={r.id} className="row-click" onClick={() => onPick(r.id)}>
              <Table.Td><Text size="sm" fw={600}>{r.name}</Text><Text size="xs" c="dimmed">{r.zones.join(", ")}</Text></Table.Td>
              <Table.Td ta="right" className="tabular" fw={600}>{fmt(r.customers_out)}</Table.Td>
              <Table.Td ta="right" className="tabular">{r.circuits_out}</Table.Td>
              <Table.Td ta="right" className="tabular">{r.open_tickets}</Table.Td>
              <Table.Td>{r.etr_at ? <Text size="sm" fw={600}>{dt(r.etr_at)}</Text> : <Text size="sm" c="dimmed">No outages</Text>}</Table.Td>
              <Table.Td><Confidence value={r.confidence} bar={data.publish_confidence} /></Table.Td>
              <Table.Td ta="right">{r.circuits_out ? <>{r.circuits_published} / {r.circuits_out}{r.circuits_ready > 0 && <Badge ml={6} size="xs" color="teal" variant="light">{r.circuits_ready} ready</Badge>}</> : "—"}</Table.Td>
            </Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed" p="sm">Region ETR = the last circuit in the region expected back. Confidence is the customer-weighted mean of its circuits. Click a region to see its circuits.</Text>
    </Card>
  );
}

/** ETRs per circuit (feeder), publishable one by one or by a confidence threshold. */
export function CircuitEtrTable({ eventId, region, onRegion }: { eventId: number; region: string | null; onRegion: (r: string | null) => void }) {
  const { can } = useAuth();
  const [zone, setZone] = useState<string | null>(null);
  const { data } = useGet<NetworkEtrs>(`/events/${eventId}/etrs`, { refetchInterval: 30_000 });
  const [bar, setBar] = useState<number | string>(80);
  const publishBar = useAction((min: number) => api.post<{ published: number }>(`/events/${eventId}/publish/circuits`, { min_confidence: min }),
    { success: r => `ETRs published for ${r.published} circuits` });
  const toggle = useAction(({ id, on }: { id: string; on: boolean }) =>
    on ? api.post(`/events/${eventId}/publish/circuits`, { feeder_ids: [id] }) : api.del(`/events/${eventId}/publish/circuits/${id}`), { success: "Website updated" });
  if (!data) return <Loading />;
  const threshold = Number(bar) || 0;
  const zones = [...new Set(data.circuits.filter(c => !region || c.region_id === region).map(c => c.zone))].sort();
  const rows = data.circuits.filter(c => (!region || c.region_id === region) && (!zone || c.zone === zone));
  const ready = data.circuits.filter(c => !c.published && c.confidence >= threshold);
  const canPublish = can("etr.publish") && data.can_publish;

  return (
    <Card padding={0}>
      <Group p="sm" justify="space-between" wrap="wrap">
        <Group gap="xs">
          <Select placeholder="All regions" clearable w={170} value={region} onChange={v => { onRegion(v); setZone(null); }}
            data={data.regions.map(r => ({ value: r.id, label: `${r.name} (${r.circuits_out})` }))} />
          <Select placeholder="All zones" clearable w={170} value={zone} onChange={setZone} data={zones} />
        </Group>
        {canPublish && (
          <Group gap="xs">
            <NumberInput w={110} min={50} max={95} step={5} suffix="%" value={bar} onChange={setBar} aria-label="Minimum confidence" />
            <Button leftSection={<IconWorldUpload size={16} />} disabled={!ready.length} loading={publishBar.isPending}
              onClick={() => modals.openConfirmModal({
                title: "Publish circuit ETRs",
                children: <Text size="sm">Publish ETRs for {ready.length} circuits at {threshold}% confidence or higher ({fmt(ready.reduce((s, c) => s + c.customers_out, 0))} customers)? Customers on these circuits see their own circuit's restoration time.</Text>,
                labels: { confirm: "Publish", cancel: "Cancel" }, onConfirm: () => publishBar.mutate(threshold),
              })}>Publish all ≥ {threshold}% ({ready.length})</Button>
          </Group>
        )}
      </Group>
      {!rows.length ? <Empty title="No circuits with open outages" /> : (
        <Table.ScrollContainer minWidth={1000}>
          <Table>
            <Table.Thead><Table.Tr>
              <Table.Th>Circuit</Table.Th><Table.Th>Substation · zone</Table.Th><Table.Th>Region</Table.Th><Table.Th ta="right">Customers out</Table.Th>
              <Table.Th ta="right">Tickets</Table.Th><Table.Th ta="right">Crews</Table.Th><Table.Th>AI ETR</Table.Th><Table.Th ta="right">Confidence</Table.Th><Table.Th>Customers see it</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map(c => (
              <Table.Tr key={c.id}>
                <Table.Td><Text size="sm" fw={600} ff="monospace">{c.id}</Text></Table.Td>
                <Table.Td><Text size="sm">{c.substation ?? "—"}</Text><Text size="xs" c="dimmed">{c.zone}</Text></Table.Td>
                <Table.Td><Text size="sm">{c.region ?? "—"}</Text></Table.Td>
                <Table.Td ta="right" className="tabular" fw={600}>{fmt(c.customers_out)}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.open_tickets}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.crews}</Table.Td>
                <Table.Td>{c.etr_at ? <Text size="sm" fw={600}>{dt(c.etr_at)}</Text> : "—"}</Table.Td>
                <Table.Td><Confidence value={c.confidence} bar={threshold} /></Table.Td>
                <Table.Td>
                  <Tooltip label={c.published ? `Published ${dt(c.published_at)}` : "Not visible to customers"}>
                    <Switch checked={c.published} disabled={!canPublish} onChange={ev => toggle.mutate({ id: c.id, on: ev.currentTarget.checked })} />
                  </Tooltip>
                </Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Text size="xs" c="dimmed" p="sm">
        Circuit confidence = how settled its tickets are (crew working 88, crew assigned 80, damage assessed 68, not yet assessed 55), less queue depth on the circuit
        and the zone's ETR misses in past events. Publish only circuits you can stand behind; the rest keep the zone-wide ETR.
      </Text>
    </Card>
  );
}

const pinColor = (c: number, bar: number) => (c >= bar ? "#3ec46d" : c >= bar - 15 ? "#f5a623" : "#f07a2e");

/** Substations with circuits out, coloured by their least certain circuit (circuit routes need the utility's GIS). */
export function CircuitMap({ eventId, region }: { eventId: number; region: string | null }) {
  const { data } = useGet<NetworkEtrs>(`/events/${eventId}/etrs`, { refetchInterval: 30_000 });
  const routes = useRoutes();
  if (!data) return null;
  const out = new Map(data.circuits.filter(c => !region || c.region_id === region).map(c => [c.id, c]));
  const lines = (routes.data?.feeders ?? []).filter(f => f.route.length).map(f => {
    const c = out.get(f.id);
    return c ? {
      id: f.id, lines: f.route, color: pinColor(c.confidence, data.publish_confidence), weight: c.published ? 5 : 3.5,
      popup: <div><b>{c.id}</b> · {c.substation} · {c.zone}<br />{fmt(c.customers_out)} out · ETR {dtShort(c.etr_at)}<br />{c.confidence}% confidence{c.published ? " · published" : ""}</div>,
    } : { id: f.id, lines: f.route, color: "#8a9aa5", weight: 1.5, opacity: 0.35 };
  }).sort((a, b) => (a.opacity ? -1 : 0) - (b.opacity ? -1 : 0));
  const imported = routes.data?.counts.imported ?? 0;
  const subs = new Map<string, typeof data.circuits>();
  for (const c of data.circuits.filter(c => !region || c.region_id === region)) {
    const k = c.substation ?? c.id;
    subs.set(k, [...(subs.get(k) ?? []), c]);
  }
  const pins = [...subs.entries()].map(([name, cs]) => {
    const worst = Math.min(...cs.map(c => c.confidence));
    return {
      id: name, lat: cs[0].lat, lng: cs[0].lng, color: pinColor(worst, data.publish_confidence),
      popup: <div><b>{name}</b> substation · {cs[0].zone}<br />{cs.map(c => (
        <div key={c.id}>{c.id}: {fmt(c.customers_out)} out · ETR {dtShort(c.etr_at)} · {c.confidence}%{c.published ? " · published" : ""}</div>))}</div>,
    };
  });
  return (
    <Card padding="sm" mb="lg">
      <TerritoryMap height={380} pins={pins} lines={lines} />
      <Group gap="md" mt={6}>
        {[["#3ec46d", `all circuits ≥ ${data.publish_confidence}%`], ["#f5a623", "some within 15 pts"], ["#f07a2e", "low confidence"]].map(([c, l]) => (
          <Group key={l} gap={4}><div style={{ width: 10, height: 10, borderRadius: 5, background: c }} /><Text size="xs" c="dimmed">{l}</Text></Group>))}
        <Text size="xs" c="dimmed">Lines are circuits with outages (thicker = published); pins are substations. {imported
          ? `${imported} routes from the utility's GIS.` : "Routes are sandbox drawings until the utility's GIS feeder export is imported (Administration → Network)."}</Text>
      </Group>
    </Card>
  );
}

/** Headline counts for the circuit view. */
export function CircuitStats({ eventId }: { eventId: number }) {
  const { data } = useGet<NetworkEtrs>(`/events/${eventId}/etrs`, { refetchInterval: 30_000 });
  if (!data) return null;
  const cs = data.circuits;
  const confident = cs.filter(c => c.confidence >= data.publish_confidence).length;
  return (
    <SimpleGrid cols={{ base: 2, md: 4 }} mb="lg">
      <Card padding="sm"><Text size="xs" c="dimmed">Circuits out</Text><Text fw={700} size="xl">{cs.length}</Text></Card>
      <Card padding="sm"><Text size="xs" c="dimmed">At ≥{data.publish_confidence}% confidence</Text><Text fw={700} size="xl" c="teal">{confident}</Text></Card>
      <Card padding="sm"><Text size="xs" c="dimmed">Published circuits</Text><Text fw={700} size="xl">{cs.filter(c => c.published).length}</Text></Card>
      <Card padding="sm"><Text size="xs" c="dimmed">Customers on published circuits</Text><Text fw={700} size="xl">{fmt(cs.filter(c => c.published).reduce((s, c) => s + c.customers_out, 0))}</Text></Card>
    </SimpleGrid>
  );
}
