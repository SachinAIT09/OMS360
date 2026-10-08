import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, Checkbox, Grid, Group, Progress, ScrollArea, SimpleGrid, Stack, Table, Text, ThemeIcon, Timeline } from "@mantine/core";
import { AreaChart } from "@mantine/charts";
import {
  IconAlertTriangle, IconBolt, IconBuildingHospital, IconClock, IconCloudStorm, IconDroplet, IconSparkles, IconTruck, IconUsers,
} from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet, useReference } from "../api/hooks";
import type { Overview, Recommendation } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { EventStatusBadge } from "../components/badges";
import { Empty, ErrorState, Loading, PageHeader, SectionTitle, Stat } from "../components/common";
import { EventLifecycle } from "../components/EventLifecycle";
import { RecommendationCard } from "../components/RecommendationCard";
import { MapLegend, TerritoryMap } from "../components/TerritoryMap";
import { ago, dt, dtShort, fmt, hoursUntil, impactWord, intensity, isRain, pct, scenario, sevColor } from "../lib/format";

export default function OverviewPage() {
  const { event } = useCurrentEvent();
  const go = useNavigate();
  const { can } = useAuth();
  const ref = useReference();
  const ov = useGet<Overview>(event ? `/events/${event.id}/overview` : null, { refetchInterval: 30_000 });
  const recs = useGet<Recommendation[]>(event ? `/events/${event.id}/recommendations` : null);
  const doneTask = useAction((id: number) => api.post(`/tasks/${id}/done`), { success: "Task completed" });

  if (!event) return <Empty title="No storm events yet" icon={<IconCloudStorm />}>Create an event or import one from the National Hurricane Center.
    <Button mt="md" onClick={() => go("/events")}>Go to Storm Events</Button></Empty>;
  if (ov.error) return <ErrorState error={ov.error} />;
  if (!ov.data || !ref.data) return <Loading />;

  const { stats: st, prediction, curve, tasks, activity } = ov.data;
  const e = ov.data.event;
  const p = prediction?.result;
  const live = ["active", "restoring", "closed"].includes(e.status);
  const h = hoursUntil(e.landfall_at);
  const open = (recs.data ?? []).filter(r => r.status === "open");
  const order = { Critical: 0, High: 1, Medium: 2 } as const;
  open.sort((a, b) => order[a.priority] - order[b.priority]);
  const idle = (st.crews_by_status.available ?? 0) + (st.crews_by_status.staged ?? 0);
  const working = (st.crews_by_status.assigned ?? 0) + (st.crews_by_status.working ?? 0);

  const zones = live
    ? st.zones.map(z => ({ id: z.id, short: z.short, lat: z.lat, lng: z.lng, customers: z.customers, value: z.pct_out, restored: z.affected > 0 && z.customers_out === 0,
        popup: <div><b>{z.name}</b><br />{fmt(z.customers_out)} out on {z.open_tickets} tickets<br />{z.crews} crews working<br />ETR {z.etr_at ? dt(z.etr_at) : "—"}{z.published ? " (published)" : ""}</div> }))
    : (p?.zones ?? []).map(z => {
        const zr = ref.data.zones.find(x => x.id === z.id)!;
        return { id: z.id, short: z.short, lat: zr.lat, lng: zr.lng, customers: z.customers, value: z.pct,
          popup: <div><b>{z.name}</b><br />Predicted {fmt(z.pred)} out ({pct(z.pct)})<br />{z.driver}<br />Restoration ~{z.eta_h} h after {impactWord(e)}</div> };
      });

  return (
    <>
      <PageHeader title={e.name} badge={<EventStatusBadge status={e.status} size="lg" />}
        description={<>{e.kind} · {intensity(e)}{!isRain(e) && ` · ${e.pressure_mb} mb`}{e.movement && ` · moving ${e.movement}`}
          {e.landfall_at && <> · {impactWord(e)} {dt(e.landfall_at)}{h != null && h > 0 && <Text span c="yellow.4" fw={600}> (in {Math.round(h)} h)</Text>}</>}</>}
        actions={<><Button variant="default" onClick={() => go(`/events/${e.id}`)}>Event details</Button><EventLifecycle event={e} /></>} />

      <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }} mb="lg">
        {live ? <>
          <Stat label="Customers out" value={fmt(st.customers_out)} color={st.customers_out ? "red" : "teal"} icon={<IconBolt size={16} />} hint={`${fmt(st.customers_affected)} affected in total`} onClick={() => go("/outages")} />
          <Stat label="Restored" value={pct(st.restored_pct)} color="teal" progress={st.restored_pct} hint="of affected customers" onClick={() => go("/restoration")} />
          <Stat label="Open tickets" value={fmt(st.open_tickets)} icon={<IconAlertTriangle size={16} />} color={st.unassigned ? "orange" : undefined} hint={`${st.unassigned} unassigned · ${st.critical_open} critical`} onClick={() => go("/outages?status=reported,assessed")} />
          <Stat label="Crews" value={`${working} / ${working + idle}`} icon={<IconTruck size={16} />} hint={`working · ${idle} idle · ${fmt(st.line_workers_on_hand)} line workers`} onClick={() => go("/crews")} />
          <Stat label="Last zone restored by" value={st.last_etr_at ? dtShort(st.last_etr_at) : "—"} icon={<IconClock size={16} />} hint="AI ETR from open tickets" onClick={() => go("/restoration")} />
          <Stat label="ETRs published" value={`${st.published_zones} / ${st.zones.filter(z => z.open_tickets).length || 0}`} hint="zones visible to customers" color={st.published_zones ? "teal" : "yellow"} onClick={() => go("/restoration")} />
        </> : <>
          <Stat label="Predicted peak outages" value={p ? fmt(p.pred_total) : "—"} color="red" icon={<IconBolt size={16} />} hint={p ? `${pct(p.pred_total / p.total_customers)} of customers · ${scenario(p)}` : "run a prediction"} onClick={() => go(`/events/${e.id}?tab=prediction`)} />
          <Stat label="Line workers" value={p ? `${fmt(p.internal.line + p.committed.line)} / ${fmt(p.required.line)}` : "—"} icon={<IconUsers size={16} />} color={p && p.needed.line > 0 ? "orange" : "teal"}
            hint={p ? (p.needed.line > 0 ? `gap ${fmt(p.needed.line)} — request mutual aid` : "requirement covered") : undefined} progress={p ? (p.internal.line + p.committed.line) / p.required.line : undefined} onClick={() => go("/crews")} />
          <Stat label="Avg restoration" value={p ? `${Math.round(p.avg_eta_h)} h` : "—"} icon={<IconClock size={16} />} hint={p ? `95% by ${p.p95_eta_h} h after ${impactWord(e)}` : undefined} />
          <Stat label="Critical facilities at risk" value={p ? p.critical_at_risk : "—"} icon={<IconBuildingHospital size={16} />} color="red" hint="hospitals, water, EOC, shelters" />
          <Stat label="Lift stations at risk" value={p ? p.lift_stations_at_risk : "—"} icon={<IconDroplet size={16} />} color="cyan" hint={p ? `${p.generators_needed} generators recommended` : undefined} />
          <Stat label="Awaiting decision" value={open.length + ov.data.pending_messages} icon={<IconSparkles size={16} />} color="ai" hint={`${open.length} recommendations · ${ov.data.pending_messages} messages`} />
        </>}
      </SimpleGrid>

      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 7.5 }}>
          <Card padding="sm">
            <SectionTitle right={<Group gap="xs"><Button size="compact-sm" variant="subtle" onClick={() => go(live ? "/outages?view=map" : `/events/${e.id}`)}>Open map</Button></Group>}>
              {live ? "Live outages by zone" : "Predicted impact by zone"}
            </SectionTitle>
            <TerritoryMap zones={zones} facilities={ref.data.facilities} yards={ref.data.yards} track={live ? null : e.track} height={430} />
            <MapLegend mode={live ? "out" : "pred"} />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4.5 }}>
          <Card padding="sm" h="100%" style={{ display: "flex", flexDirection: "column" }}>
            <SectionTitle right={<Badge color="ai" variant="light">{open.length} open</Badge>}>
              <Group gap={6}><ThemeIcon size="sm" color="ai" variant="light"><IconSparkles size={14} /></ThemeIcon>What we need to do</Group>
            </SectionTitle>
            <ScrollArea.Autosize mah={470}>
              <Stack gap="xs">
                {open.length ? open.map(r => <RecommendationCard key={r.id} r={r} />) : <Empty title="Nothing needs a decision">New recommendations appear as the storm develops.</Empty>}
                {(recs.data ?? []).filter(r => r.status !== "open").slice(0, 3).map(r => <RecommendationCard key={r.id} r={r} />)}
              </Stack>
            </ScrollArea.Autosize>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7.5 }}>
          {live && curve ? (
            <Card padding="md">
              <SectionTitle>Restoration progress</SectionTitle>
              {curve.points.length ? (
                <AreaChart h={240} data={curve.points.map(pt => ({ t: dtShort(pt.at), "Customers out": pt.out, "Restored %": Math.round(pt.restored_pct * 100) }))}
                  dataKey="t" series={[{ name: "Customers out", color: "red.6" }]} curveType="monotone" withDots={false} gridAxis="y" tickLine="none" valueFormatter={v => fmt(v)} />
              ) : <Empty title="No outages yet">Tickets appear here as smart meters report outages.</Empty>}
            </Card>
          ) : (
            <Card padding={0}>
              <Group p="md" pb="xs" justify="space-between"><Text fw={600}>Predicted outages by zone</Text>
                {prediction && <Text size="xs" c="dimmed">Prediction run {ago(prediction.created_at)} · {scenario(prediction.result)}</Text>}</Group>
              {p ? (
                <Table>
                  <Table.Thead><Table.Tr><Table.Th>Zone</Table.Th><Table.Th ta="right">Customers</Table.Th><Table.Th ta="right">Predicted out</Table.Th><Table.Th w={140} /><Table.Th>Main driver</Table.Th><Table.Th ta="right">Restore</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>{[...p.zones].sort((a, b) => b.pred - a.pred).slice(0, 8).map(z => (
                    <Table.Tr key={z.id}><Table.Td>{z.short}</Table.Td><Table.Td ta="right" className="tabular">{fmt(z.customers)}</Table.Td>
                      <Table.Td ta="right" className="tabular" fw={600} c={sevColor(z.pct)}>{fmt(z.pred)}</Table.Td>
                      <Table.Td><Progress value={z.pct * 125} color={sevColor(z.pct)} size="sm" /></Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{z.driver}</Text></Table.Td><Table.Td ta="right" className="tabular">{z.eta_h} h</Table.Td></Table.Tr>))}
                  </Table.Tbody>
                </Table>
              ) : <Empty title="No prediction yet">{can("predictions.run") && <Button mt="sm" onClick={() => go(`/events/${e.id}?tab=prediction`)}>Run a prediction</Button>}</Empty>}
            </Card>
          )}
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4.5 }}>
          <Card padding="md" h="100%">
            <SectionTitle right={<Badge variant="light" color="gray">{tasks.filter(t => t.status === "open").length} open</Badge>}>Tasks</SectionTitle>
            <Stack gap={8}>
              {tasks.length ? tasks.slice(0, 7).map(t => (
                <Group key={t.id} gap="sm" wrap="nowrap" align="flex-start">
                  <Checkbox checked={t.status === "done"} disabled={t.status === "done" || !can("tasks.manage")} onChange={() => doneTask.mutate(t.id)} mt={2} />
                  <div style={{ flex: 1 }}>
                    <Text size="sm" td={t.status === "done" ? "line-through" : undefined} c={t.status === "done" ? "dimmed" : undefined}>{t.title}</Text>
                    <Text size="xs" c="dimmed">{t.status === "done" ? `Done ${ago(t.done_at)}` : `Due ${dt(t.due_at)}`}</Text>
                  </div>
                </Group>)) : <Text size="sm" c="dimmed">Tasks created from approved recommendations show up here.</Text>}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={12}>
          <Card padding="md" h="100%">
            <SectionTitle>Activity</SectionTitle>
            <ScrollArea.Autosize mah={330}>
              <Timeline bulletSize={10} lineWidth={1}>
                {activity.map(a => (
                  <Timeline.Item key={a.id}>
                    <Text size="sm">{a.detail || a.action}</Text>
                    <Text size="xs" c="dimmed">{a.user} · {ago(a.at)}</Text>
                  </Timeline.Item>))}
              </Timeline>
            </ScrollArea.Autosize>
          </Card>
        </Grid.Col>
      </Grid>
    </>
  );
}
