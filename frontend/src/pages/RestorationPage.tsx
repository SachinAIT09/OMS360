import { Alert, Badge, Button, Card, Grid, Group, Progress, SimpleGrid, Switch, Table, Text, Tooltip } from "@mantine/core";
import { AreaChart } from "@mantine/charts";
import { modals } from "@mantine/modals";
import { IconInfoCircle, IconWorldUpload } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet } from "../api/hooks";
import type { Curve, EventStats, StormEvent } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { Empty, Loading, PageHeader, SectionTitle, Stat } from "../components/common";
import { MapLegend, TerritoryMap } from "../components/TerritoryMap";
import { dt, dtShort, fmt, pct, sevColor } from "../lib/format";

interface Resto { event: StormEvent; stats: EventStats; curve: Curve; prediction: { avg_eta_h: number; p95_eta_h: number; zones: Record<string, number> } | null; can_publish: boolean }

export default function RestorationPage() {
  const { event } = useCurrentEvent();
  const { can } = useAuth();
  const { data } = useGet<Resto>(event ? `/events/${event.id}/restoration` : null, { refetchInterval: 30_000 });
  const publishAll = useAction(() => api.post<{ published: number }>(`/events/${event!.id}/publish`, {}), { success: r => `ETRs published for ${r.published} zones — customers notified` });
  const toggle = useAction(({ zone, on }: { zone: string; on: boolean }) =>
    on ? api.post(`/events/${event!.id}/publish`, { zone_ids: [zone] }) : api.del(`/events/${event!.id}/publish/${zone}`), { success: "Website updated" });
  if (!event) return <Empty title="Select a storm event" />;
  if (!data) return <Loading />;
  const st = data.stats;
  const zones = [...st.zones].sort((a, b) => (b.customers_out - a.customers_out) || a.short.localeCompare(b.short));
  const active = zones.filter(z => z.open_tickets);
  const unpublished = active.filter(z => !z.published).length;

  return (
    <>
      <PageHeader title="Restoration & ETR" description="Estimated restoration times computed from open tickets, assigned crews and damage type. Publishing makes them visible to customers."
        actions={can("etr.publish") && data.can_publish && <Button leftSection={<IconWorldUpload size={16} />} disabled={!unpublished}
          onClick={() => modals.openConfirmModal({ title: "Publish restoration times", children: <Text size="sm">Publish ETRs for {unpublished} zones to the public outage map and send ETR text messages to affected customers?</Text>,
            labels: { confirm: "Publish", cancel: "Cancel" }, onConfirm: () => publishAll.mutate() })}>Publish all ({unpublished})</Button>} />
      {!data.can_publish && <Alert icon={<IconInfoCircle size={18} />} mb="md" color="gray">ETRs can be published while the event is Active or Restoring. {data.prediction && `Predicted restoration: average ${Math.round(data.prediction.avg_eta_h)} h, 95% within ${data.prediction.p95_eta_h} h of landfall.`}</Alert>}
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="lg">
        <Stat label="Customers out" value={fmt(st.customers_out)} color="red" hint={`${st.open_tickets} open tickets`} />
        <Stat label="Restored" value={pct(st.restored_pct)} color="teal" progress={st.restored_pct} hint={`${fmt(st.customers_affected - st.customers_out)} of ${fmt(st.customers_affected)}`} />
        <Stat label="Last zone expected" value={st.last_etr_at ? dtShort(st.last_etr_at) : "—"} hint={data.prediction ? `model predicted ${data.prediction.p95_eta_h} h after landfall` : undefined} />
        <Stat label="Published zones" value={`${st.published_zones} / ${active.length}`} color={unpublished ? "yellow" : "teal"} hint="visible on the public outage map" />
      </SimpleGrid>
      <Grid gutter="lg" mb="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card>
            <SectionTitle>Restoration curve</SectionTitle>
            {data.curve.points.length ? (
              <AreaChart h={300} data={data.curve.points.map(p => ({ t: dtShort(p.at), "Restored %": Math.round(p.restored_pct * 100), "Customers out": p.out }))} dataKey="t"
                series={[{ name: "Restored %", color: "teal.6" }]} curveType="monotone" withDots={false} yAxisProps={{ domain: [0, 100] }} unit="%" gridAxis="y" />
            ) : <Empty title="No outages recorded for this event yet" />}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card padding="sm">
            <TerritoryMap height={300} zones={st.zones.map(z => ({ id: z.id, short: z.short, lat: z.lat, lng: z.lng, customers: z.customers, value: z.pct_out,
              restored: z.affected > 0 && !z.customers_out, popup: <div><b>{z.name}</b><br />{fmt(z.customers_out)} out<br />ETR {dt(z.etr_at)}</div> }))} />
            <MapLegend />
          </Card>
        </Grid.Col>
      </Grid>
      <Card padding={0}>
        <Table.ScrollContainer minWidth={950}>
          <Table>
            <Table.Thead><Table.Tr>
              <Table.Th>Zone</Table.Th><Table.Th ta="right">Customers out</Table.Th><Table.Th w={160}>Share out</Table.Th><Table.Th ta="right">Open tickets</Table.Th>
              <Table.Th ta="right">Crews</Table.Th><Table.Th>AI ETR</Table.Th><Table.Th ta="right">Confidence</Table.Th><Table.Th>Customers see it</Table.Th>
            </Table.Tr></Table.Thead>
            <Table.Tbody>{zones.map(z => (
              <Table.Tr key={z.id}>
                <Table.Td><Text size="sm" fw={500}>{z.name}</Text><Group gap={4}>{z.coastal && <Badge size="xs" variant="outline">surge</Badge>}{z.critical && <Badge size="xs" color="red" variant="outline">hospital</Badge>}{z.medical && <Badge size="xs" color="ai" variant="outline">medical</Badge>}</Group></Table.Td>
                <Table.Td ta="right" className="tabular" fw={600} c={z.customers_out ? sevColor(z.pct_out) : "teal"}>{fmt(z.customers_out)}</Table.Td>
                <Table.Td><Progress value={z.pct_out * 200} color={sevColor(z.pct_out)} size="sm" /></Table.Td>
                <Table.Td ta="right" className="tabular">{z.open_tickets}</Table.Td>
                <Table.Td ta="right" className="tabular">{z.crews}</Table.Td>
                <Table.Td>{z.etr_at ? <Text size="sm" fw={600}>{dt(z.etr_at)}</Text> : z.affected ? <Badge color="teal">Restored</Badge> : <Text size="sm" c="dimmed">No outages</Text>}</Table.Td>
                <Table.Td ta="right">{z.confidence != null ? `${z.confidence}%` : "—"}</Table.Td>
                <Table.Td>
                  {z.open_tickets ? (
                    <Tooltip label={z.published ? `Published ${dt(z.published_at)}` : "Not visible to customers"}>
                      <Switch checked={z.published} disabled={!can("etr.publish") || !data.can_publish} onChange={ev => toggle.mutate({ zone: z.id, on: ev.currentTarget.checked })} />
                    </Tooltip>
                  ) : <Text size="xs" c="dimmed">—</Text>}
                </Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Text size="xs" c="dimmed" p="sm">ETR = remaining work in the zone (job hours by damage type; storm surge ×2.3) ÷ crews working there plus a share of idle crews. Assigned tickets use their committed ETR. Recalculated whenever tickets or crews change.</Text>
      </Card>
    </>
  );
}
