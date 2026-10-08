import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Alert, Badge, Button, Card, Grid, Group, NumberInput, SegmentedControl, SimpleGrid, Stack, Table, Tabs, Text, Textarea, Timeline,
} from "@mantine/core";
import { BarChart } from "@mantine/charts";
import { DateTimePicker } from "@mantine/dates";
import { IconChartDots, IconInfoCircle, IconListDetails, IconMap, IconPlayerPlay } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet, useReference } from "../api/hooks";
import type { PredictionRun, StormEvent, EventStats, Audit } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { EventStatusBadge } from "../components/badges";
import { ErrorState, Loading, PageHeader, SectionTitle, Stat } from "../components/common";
import { EventLifecycle } from "../components/EventLifecycle";
import { ForecastCard, PredictedEtrTables } from "../components/PredictionNetwork";
import { MapLegend, TerritoryMap } from "../components/TerritoryMap";
import { ago, dt, fmt, impactWord, isRain, pct, scenario, sevColor } from "../lib/format";

type Detail = StormEvent & { prediction: PredictionRun | null; stats: EventStats };

export default function EventDetailPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const { data: e, error } = useGet<Detail>(`/events/${id}`);
  const go = useNavigate();
  if (error) return <ErrorState error={error} />;
  if (!e) return <Loading />;
  return (
    <>
      <PageHeader title={e.name} badge={<EventStatusBadge status={e.status} size="lg" />}
        description={<>{e.kind} · {e.source === "nhc" ? `NHC ${e.nhc_id?.toUpperCase()}` : "Manual event"} · created {ago(e.created_at)}</>}
        actions={<><Button variant="default" onClick={() => go("/")}>Open overview</Button><EventLifecycle event={e} /></>} />
      <Tabs value={tab} onChange={v => setParams(v === "overview" ? {} : { tab: v! })} keepMounted={false}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="overview" leftSection={<IconMap size={16} />}>Storm</Tabs.Tab>
          <Tabs.Tab value="prediction" leftSection={<IconChartDots size={16} />}>Impact prediction</Tabs.Tab>
          <Tabs.Tab value="timeline" leftSection={<IconListDetails size={16} />}>Timeline</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="overview"><StormTab e={e} /></Tabs.Panel>
        <Tabs.Panel value="prediction"><PredictionTab e={e} /></Tabs.Panel>
        <Tabs.Panel value="timeline"><TimelineTab id={e.id} /></Tabs.Panel>
      </Tabs>
    </>
  );
}

function StormTab({ e }: { e: Detail }) {
  const { can } = useAuth();
  const ref = useReference();
  const [cat, setCat] = useState<number | string>(e.category);
  const [wind, setWind] = useState<number | string>(e.max_wind_mph);
  const [lf, setLf] = useState<Date | null>(e.landfall_at ? new Date(e.landfall_at) : null);
  const [notes, setNotes] = useState(e.notes);
  const rain = isRain(e);
  const [rainIn, setRainIn] = useState<number | string>(e.rain_total_in ?? 4);
  const [rate, setRate] = useState<number | string>(e.rain_rate_in_hr ?? 1);
  const [sat, setSat] = useState<number | string>(Math.round((e.soil_saturation ?? 0.5) * 100));
  const save = useAction(() => api.patch(`/events/${e.id}`, rain
    ? { rain_total_in: Number(rainIn), rain_rate_in_hr: Number(rate), soil_saturation: Number(sat) / 100, landfall_at: lf?.toISOString() ?? null, notes }
    : { category: Number(cat), max_wind_mph: Number(wind), landfall_at: lf?.toISOString() ?? null, notes }),
    { success: "Event updated" });
  const params: [string, string][] = rain
    ? [["Type", e.kind], ["Rainfall forecast", `${e.rain_total_in ?? "—"} in`], ["Peak rate", `${e.rain_rate_in_hr ?? "—"} in/hr`],
       ["Duration", `${e.duration_h ?? "—"} h`], ["Soil saturation", pct(e.soil_saturation)], ["Rain onset", dt(e.landfall_at)],
       ["Activated", dt(e.activated_at)], ["Closed", dt(e.closed_at)]]
    : [["Type", e.kind], ["Category", `Cat ${e.category}`], ["Max sustained wind", `${e.max_wind_mph} mph`], ["Pressure", `${e.pressure_mb} mb`],
       ["Position", `${e.lat.toFixed(1)}°, ${e.lng.toFixed(1)}°`], ["Movement", e.movement || "—"], ["Landfall", dt(e.landfall_at)],
       ["Activated", dt(e.activated_at)], ["Closed", dt(e.closed_at)]];
  return (
    <Grid gutter="lg">
      <Grid.Col span={{ base: 12, lg: 8 }}>
        <Card padding="sm">
          <TerritoryMap track={e.track} zones={[]} facilities={ref.data?.facilities} center={[e.track?.[0]?.lat ?? e.lat, e.track?.[0]?.lng ?? e.lng]} zoom={rain ? 9 : 6} height={520} />
          <Text size="xs" c="dimmed" mt={6}>{rain ? "Rain events cover the whole service territory; critical facilities shown." : "White = observed track · amber dashed = forecast track · rings widen with forecast uncertainty."}</Text>
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 4 }}>
        <Stack>
          <Card>
            <SectionTitle>Current parameters</SectionTitle>
            <Table fz="sm" verticalSpacing={6}><Table.Tbody>
              {params.map(([k, v]) =>
                <Table.Tr key={k}><Table.Td c="dimmed">{k}</Table.Td><Table.Td fw={500} ta="right">{v}</Table.Td></Table.Tr>)}
            </Table.Tbody></Table>
          </Card>
          {can("events.manage") && e.status !== "closed" && (
            <Card>
              <SectionTitle>{rain ? "Update from latest rainfall forecast" : "Update from latest advisory"}</SectionTitle>
              <Stack gap="xs">
                {rain ? <Group grow>
                  <NumberInput label="Rainfall (in)" min={0.5} max={40} decimalScale={1} value={rainIn} onChange={setRainIn} />
                  <NumberInput label="Peak (in/hr)" min={0.1} max={8} decimalScale={1} step={0.25} value={rate} onChange={setRate} />
                  <NumberInput label="Soil" min={0} max={100} suffix="%" value={sat} onChange={setSat} />
                </Group> : <Group grow><NumberInput label="Category" min={1} max={5} value={cat} onChange={setCat} /><NumberInput label="Max wind (mph)" value={wind} onChange={setWind} /></Group>}
                <DateTimePicker label={rain ? "Rain onset" : "Expected landfall"} value={lf} onChange={setLf} clearable valueFormat="ddd MMM D, h:mm A" />
                <Textarea label="Notes" autosize minRows={2} value={notes} onChange={ev => setNotes(ev.currentTarget.value)} />
                <Button onClick={() => save.mutate()} loading={save.isPending}>Save changes</Button>
              </Stack>
            </Card>
          )}
          {e.notes && <Alert icon={<IconInfoCircle size={18} />} color="gray">{e.notes}</Alert>}
        </Stack>
      </Grid.Col>
    </Grid>
  );
}

function PredictionTab({ e }: { e: Detail }) {
  const { can } = useAuth();
  const ref = useReference();
  const runs = useGet<{ id: number; category: number; scenario?: string; created_at: string; created_by: string; pred_total: number; required_line: number }[]>(`/events/${e.id}/predictions`);
  const rain = isRain(e);
  const hasForecast = !!e.prediction?.result.forecast;
  const [cat, setCat] = useState(hasForecast ? "fc" : String(rain ? e.prediction?.result.rain_in ?? e.rain_total_in ?? 4 : e.prediction?.category ?? e.category));
  const [preview, setPreview] = useState<PredictionRun | null>(null);
  const run = useAction((save: boolean) => api.post<PredictionRun>(`/events/${e.id}/predictions`,
    cat === "fc" ? { save } : rain ? { rain_in: Number(cat), save } : { category: Number(cat), save }),
    { success: r => r.id ? `Prediction saved: ${fmt(r.result.pred_total)} customers` : "Scenario calculated (not saved)", invalidate: ["/events"] });
  const shown = preview ?? e.prediction;
  const p = shown?.result;

  return (
    <Stack>
      <Card>
        <Group justify="space-between" wrap="wrap">
          <Group gap="lg">
            <div>
              <Text size="sm" fw={600}>{rain ? "Scenario: total rainfall" : "Scenario: intensity at landfall"}</Text>
              <SegmentedControl mt={6} value={cat} onChange={setCat}
                data={[...(hasForecast || cat === "fc" ? [{ value: "fc", label: "Parent forecast" }] : []),
                  ...(rain ? [...new Set(["2", "4", "6", "8", "12", cat])].filter(r => r !== "fc").sort((a, b) => Number(a) - Number(b)).map(r => ({ value: r, label: `${r} in` }))
                    : ["1", "2", "3", "4", "5"].map(c => ({ value: c, label: `Cat ${c}` })))]} />
            </div>
            <Text size="sm" c="dimmed" maw={460}>{rain
              ? "Model inputs: forecast rainfall, peak rate and soil saturation, zone flood exposure and tree canopy, feeder overhead exposure, rostered crews and mutual aid requested."
              : "Model inputs: forecast wind and surge, zone vulnerability, feeder overhead exposure and vegetation cycle, rostered crews and mutual aid requested, calibrated on Irma (2017), Ian (2022) and Milton (2024) damage in the territory."}</Text>
          </Group>
          {can("predictions.run") && (
            <Group gap="xs">
              <Button variant="default" onClick={async () => setPreview(await run.mutateAsync(false))} loading={run.isPending}>Try scenario</Button>
              <Button leftSection={<IconPlayerPlay size={16} />} onClick={async () => { await run.mutateAsync(true); setPreview(null); }} loading={run.isPending}>Run & save prediction</Button>
            </Group>
          )}
        </Group>
        {preview && <Alert mt="sm" color="yellow" p="xs">Showing an unsaved {scenario(preview.result)} scenario. <Button size="compact-xs" variant="subtle" onClick={() => setPreview(null)}>Back to saved prediction</Button></Alert>}
      </Card>
      <ForecastCard eventId={e.id} rain={rain} canRun={can("predictions.run")} />

      {!p ? <Card><Text c="dimmed">No prediction yet.</Text></Card> : <>
        <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }}>
          <Stat label="Predicted peak" value={fmt(p.pred_total)} color="red" hint={`${pct(p.pred_total / p.total_customers)} of customers`} />
          <Stat label="Line workers needed" value={fmt(p.required.line)} hint={`${fmt(p.internal.line)} rostered · ${fmt(p.committed.line)} requested`} />
          <Stat label="Still to request" value={fmt(p.needed.line)} color={p.needed.line ? "orange" : "teal"} hint={`+ ${fmt(p.needed.tree)} tree, ${fmt(p.needed.da)} assessors`} />
          <Stat label="95% restored" value={`${p.p95_eta_h} h`} hint={`avg ${Math.round(p.avg_eta_h)} h after ${impactWord(e)}`} />
          <Stat label="Model confidence" value={`${p.confidence}%`} color="ai" hint={p.forecast ? `on ${p.forecast.source}` : "back-tested MAPE 11%"} />
          <Stat label="Water customers at risk" value={fmt(p.water_customers_at_risk)} color="cyan" hint={`${p.lift_stations_at_risk} lift stations`} />
        </SimpleGrid>
        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card padding="sm">
              <TerritoryMap height={420} facilities={ref.data?.facilities} zones={p.zones.map(z => {
                const zr = ref.data?.zones.find(x => x.id === z.id);
                return { id: z.id, short: z.short, lat: zr?.lat ?? 0, lng: zr?.lng ?? 0, customers: z.customers, value: z.pct,
                  popup: <div><b>{z.name}</b><br />Predicted {fmt(z.pred)} ({pct(z.pct)})<br />{z.driver}</div> };
              })} />
              <MapLegend mode="pred" />
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card padding={0}>
              <Table>
                <Table.Thead><Table.Tr><Table.Th>Zone</Table.Th><Table.Th ta="right">Predicted out</Table.Th><Table.Th ta="right">%</Table.Th><Table.Th>Driver</Table.Th><Table.Th ta="right">Restore</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{[...p.zones].sort((a, b) => b.pred - a.pred).map(z => (
                  <Table.Tr key={z.id}><Table.Td>{z.short}</Table.Td><Table.Td ta="right" className="tabular">{fmt(z.pred)}</Table.Td>
                    <Table.Td ta="right" fw={600} c={sevColor(z.pct)}>{pct(z.pct)}</Table.Td><Table.Td><Text size="xs" c="dimmed">{z.driver}</Text>
                      {z.hazard && <Text size="xs" c="dimmed">{rain ? `${z.hazard.rain_in} in rain` : `gust ${Math.round(z.hazard.gust_mph ?? 0)} mph${z.hazard.surge_ft ? ` · surge ${z.hazard.surge_ft} ft` : ""}`}</Text>}</Table.Td>
                    <Table.Td ta="right">{z.eta_h} h</Table.Td></Table.Tr>))}
                </Table.Tbody>
              </Table>
            </Card>
          </Grid.Col>
        </Grid>
        <PredictedEtrTables p={p} impactAt={e.landfall_at} impactWord={impactWord(e)} />
        <Card>
          <SectionTitle right={<Badge color="red" variant="light">Top 8 feeders = {pct(p.feeders.slice(0, 8).reduce((s, f) => s + f.pred, 0) / p.pred_total)} of predicted impact</Badge>}>
            80 / 20 — feeders driving the impact
          </SectionTitle>
          <BarChart h={240} data={p.feeders.slice(0, 24).map((f, i) => ({ feeder: f.id, "Customers": f.pred, top: i < 8 }))} dataKey="feeder"
            series={[{ name: "Customers", color: "red.6" }]} tickLine="none" gridAxis="y" valueFormatter={v => fmt(v)} xAxisProps={{ angle: -40, textAnchor: "end", height: 60, interval: 0, fontSize: 10 }} />
          <Text size="xs" c="dimmed" mt="xs">Weighted by customers, overhead exposure, vegetation cycle and zone vulnerability. Pre-assign crews and materials to these feeders first; they're also the best hardening candidates.</Text>
        </Card>
        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <Card padding={0}>
              <Text fw={600} p="md" pb={0}>Critical facilities</Text>
              <Table mt="xs">
                <Table.Thead><Table.Tr><Table.Th>Facility</Table.Th><Table.Th>Feeder</Table.Th><Table.Th>Risk</Table.Th><Table.Th>Backup power</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{p.facilities.map(f => (
                  <Table.Tr key={f.id}><Table.Td>{f.name}<Text size="xs" c="dimmed">{f.type}</Text></Table.Td><Table.Td>{f.feeder}</Table.Td>
                    <Table.Td><Badge color={f.risk === "High" ? "red" : f.risk === "Medium" ? "orange" : "teal"}>{f.risk}</Badge></Table.Td><Table.Td><Text size="xs">{f.backup}</Text></Table.Td></Table.Tr>))}
                </Table.Tbody>
              </Table>
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <Stack>
              <Card>
                <SectionTitle>Water system</SectionTitle>
                <SimpleGrid cols={2}>
                  <div><Text size="xs" c="dimmed">Lift stations at risk</Text><Text fw={600}>{p.lift_stations_at_risk} / {p.lift_stations_total}</Text></div>
                  <div><Text size="xs" c="dimmed">Generators needed</Text><Text fw={600}>{p.generators_needed}</Text></div>
                </SimpleGrid>
                <Text size="sm" mt="sm" c="dimmed">{p.boil_water_zones.length ? `Precautionary boil-water notices likely for ${p.boil_water_zones.join(", ")}.` : "No boil-water notices expected."}</Text>
              </Card>
              <Card>
                <SectionTitle>Materials</SectionTitle>
                <SimpleGrid cols={3}>
                  <div><Text size="xs" c="dimmed">Poles</Text><Text fw={600}>{fmt(p.materials.poles)}</Text></div>
                  <div><Text size="xs" c="dimmed">Transformers</Text><Text fw={600}>{fmt(p.materials.transformers)}</Text></div>
                  <div><Text size="xs" c="dimmed">Conductor</Text><Text fw={600}>{fmt(p.materials.conductor_miles)} mi</Text></div>
                </SimpleGrid>
              </Card>
            </Stack>
          </Grid.Col>
        </Grid>
      </>}

      <Card padding={0}>
        <Text fw={600} p="md" pb={0}>Prediction history</Text>
        <Table mt="xs">
          <Table.Thead><Table.Tr><Table.Th>Run</Table.Th><Table.Th>Scenario</Table.Th><Table.Th ta="right">Predicted out</Table.Th><Table.Th ta="right">Line workers needed</Table.Th><Table.Th>By</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{(runs.data ?? []).map((r, i) => (
            <Table.Tr key={r.id}><Table.Td>{dt(r.created_at)} {i === 0 && <Badge size="xs" ml={4}>current</Badge>}</Table.Td><Table.Td>{r.scenario ?? `Cat ${r.category}`}</Table.Td>
              <Table.Td ta="right" className="tabular">{fmt(r.pred_total)}</Table.Td><Table.Td ta="right" className="tabular">{fmt(r.required_line)}</Table.Td><Table.Td>{r.created_by}</Table.Td></Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}

function TimelineTab({ id }: { id: number }) {
  const { data } = useGet<Audit[]>(`/events/${id}/timeline`);
  if (!data) return <Loading />;
  return (
    <Card>
      <Timeline bulletSize={12} lineWidth={2}>
        {data.map(a => (
          <Timeline.Item key={a.id} title={<Text size="sm" fw={500}>{a.detail || a.action}</Text>}>
            <Text size="xs" c="dimmed">{a.user} · {a.action} · {dt(a.at)}</Text>
          </Timeline.Item>))}
      </Timeline>
    </Card>
  );
}
