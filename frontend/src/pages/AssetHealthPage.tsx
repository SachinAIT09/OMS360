import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert, Badge, Button, Card, Drawer, Grid, Group, Modal, Pagination, Progress, SegmentedControl, Select, SimpleGrid, Slider, Stack, Switch, Table, Tabs,
  Text, Textarea, Tooltip,
} from "@mantine/core";
import { BarChart, LineChart } from "@mantine/charts";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { IconActivityHeartbeat, IconBolt, IconBuildingFactory2, IconCash, IconFileUpload, IconInfoCircle } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet, useRoutes } from "../api/hooks";
import type {
  Asset, AssetSummary, CircuitHealth, CircuitHealthDetail, Condition, PredCircuit, PredictionRun, ReplacementPlan, StormEvent, SubstationAsset,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { Loading, PageHeader, SectionTitle, Stat } from "../components/common";
import { TerritoryMap } from "../components/TerritoryMap";
import { fmt, money, pct } from "../lib/format";
import { PROFILE } from "../lib/profile";

const BAND_COLOR: Record<Condition, string> = { Good: "teal", Fair: "yellow", Poor: "orange", Critical: "red" };
const BANDS: Condition[] = ["Good", "Fair", "Poor", "Critical"];
/** Health-index colour scale (0 end of life … 100 as new), shared by the map and tables. */
const hiColor = (hi: number) => (hi >= 70 ? "#3ec46d" : hi >= 55 ? "#f5a623" : hi >= 40 ? "#f07a2e" : "#e0506a");

function HealthBadge({ hi, condition }: { hi: number; condition: Condition }) {
  return <Badge variant="light" color={BAND_COLOR[condition]} style={{ textTransform: "none" }}>HI {Math.round(hi)} · {condition}</Badge>;
}

/** Share of each condition band as one stacked bar. */
function BandBar({ bands }: { bands: Record<Condition, number> }) {
  const total = BANDS.reduce((s, b) => s + (bands[b] ?? 0), 0) || 1;
  return (
    <>
      <Progress.Root size={14}>
        {BANDS.map(b => (
          <Tooltip key={b} label={`${b}: ${fmt(bands[b])} (${pct((bands[b] ?? 0) / total)})`}>
            <Progress.Section value={((bands[b] ?? 0) / total) * 100} color={BAND_COLOR[b]} />
          </Tooltip>))}
      </Progress.Root>
      <Group gap="md" mt={6}>{BANDS.map(b => <Text key={b} size="xs" c="dimmed"><Text span c={`${BAND_COLOR[b]}.5`} fw={700}>■</Text> {b} {pct((bands[b] ?? 0) / total)}</Text>)}</Group>
    </>
  );
}

export default function AssetHealthPage() {
  const [params, setParams] = useSearchParams();
  const region = params.get("region");
  const circuit = params.get("circuit");
  const tab = params.get("tab") ?? "circuits";
  const set = (k: string, v: string | null) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  const { can } = useAuth();
  const [importOpen, importCtl] = useDisclosure(false);
  const { data: sm } = useGet<AssetSummary>("/assets/summary");
  if (!sm) return <Loading />;
  const d = sm.distribution, p = sm.power;

  return (
    <>
      <PageHeader title="Asset health" description={`Transformer age and condition across ${PROFILE.utility}, by region, circuit and substation — and how it changes storm risk.`}
        actions={can("assets.manage") && <Button variant="default" leftSection={<IconFileUpload size={16} />} onClick={importCtl.open}>Import asset register</Button>} />
      <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }} mb="lg">
        <Stat label="Distribution transformers" value={fmt(d.xfmrs)} hint={`mean age ${d.mean_age} y · oldest ${d.oldest} y`} icon={<IconBolt size={16} />} />
        <Stat label="Poor or critical" value={fmt(d.poor)} color="orange" hint={`${pct(d.pct_poor)} of the fleet · ${fmt(d.critical)} critical`} progress={d.pct_poor} />
        <Stat label="Past design life" value={pct(d.pct_over_life)} color="yellow" hint="35 y pole-mount · 40 y pad-mount" />
        <Stat label="Expected failures, 12 mo" value={fmt(d.expected_failures + p.expected_failures)} color="red" hint="Weibull on effective age" />
        <Stat label="Substation transformers" value={fmt(p.xfmrs)} icon={<IconBuildingFactory2 size={16} />} hint={`${p.poor} poor/critical · mean age ${p.mean_age} y`} />
        <Stat label="Replacement backlog" value={money(sm.replacement_capex)} icon={<IconCash size={16} />} color="ai" hint="Poor + Critical units at today's cost" />
      </SimpleGrid>

      <Grid gutter="lg" mb="lg">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card h="100%">
            <SectionTitle>Distribution transformers by age</SectionTitle>
            <BarChart h={200} data={sm.age_histogram} dataKey="decade" series={[{ name: "count", label: "Transformers", color: "brand.5" }]}
              tickLine="none" gridAxis="y" valueFormatter={v => fmt(v)} />
            <Text size="sm" fw={600} mt="md" mb={6}>Condition — distribution</Text>
            <BandBar bands={sm.bands} />
            <Text size="sm" fw={600} mt="md" mb={6}>Condition — substation power transformers</Text>
            <BandBar bands={sm.power_bands} />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card padding={0} h="100%">
            <Text fw={600} p="md" pb={0}>By region</Text>
            <Table.ScrollContainer minWidth={720}>
              <Table mt="xs" highlightOnHover>
                <Table.Thead><Table.Tr><Table.Th>Region</Table.Th><Table.Th ta="right">Circuits</Table.Th><Table.Th ta="right">Transformers</Table.Th>
                  <Table.Th ta="right">Mean age</Table.Th><Table.Th ta="right">Health</Table.Th><Table.Th ta="right">Poor / critical</Table.Th>
                  <Table.Th ta="right">Failures / yr</Table.Th><Table.Th ta="right">Substation units</Table.Th><Table.Th ta="right">Backlog</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{sm.regions.map(r => (
                  <Table.Tr key={r.id} className="row-click" onClick={() => set("region", region === r.id ? null : r.id)}
                    bg={region === r.id ? "var(--mantine-color-default-hover)" : undefined}>
                    <Table.Td fw={600}>{r.name}</Table.Td>
                    <Table.Td ta="right" className="tabular">{r.circuits}</Table.Td>
                    <Table.Td ta="right" className="tabular">{fmt(r.xfmrs)}</Table.Td>
                    <Table.Td ta="right" className="tabular">{r.mean_age} y</Table.Td>
                    <Table.Td ta="right" className="tabular" fw={600} c={hiColor(r.mean_hi)}>{Math.round(r.mean_hi)}</Table.Td>
                    <Table.Td ta="right" className="tabular">{fmt(r.poor)} <Text span size="xs" c="dimmed">({pct(r.pct_poor)})</Text></Table.Td>
                    <Table.Td ta="right" className="tabular">{fmt(r.expected_failures)}</Table.Td>
                    <Table.Td ta="right" className="tabular">{r.power_transformers} <Text span size="xs" c={r.power_poor ? "orange.5" : "dimmed"}>({r.power_poor} poor)</Text></Table.Td>
                    <Table.Td ta="right" className="tabular">{money(r.replacement_capex)}</Table.Td>
                  </Table.Tr>))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            <Text size="xs" c="dimmed" p="sm">Click a region to filter the circuits and substations below. Health index (HI) 0–100: age against design life, inspection score,
              loading and — for substation units — dissolved gas, oil moisture, through-faults and maintenance.</Text>
          </Card>
        </Grid.Col>
      </Grid>

      <Tabs value={tab} onChange={v => set("tab", v === "circuits" ? null : v)} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="circuits">Circuits</Tabs.Tab>
          <Tabs.Tab value="substations">Substation transformers</Tabs.Tab>
          <Tabs.Tab value="risk">Highest-risk units</Tabs.Tab>
          <Tabs.Tab value="plan">Replacement plan</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="circuits"><CircuitsTab region={region} onOpen={id => set("circuit", id)} regionName={sm.regions.find(r => r.id === region)?.name} /></Tabs.Panel>
        <Tabs.Panel value="substations"><SubstationsTab region={region} /></Tabs.Panel>
        <Tabs.Panel value="risk"><AssetTable rows={sm.top_risk} showWhere title="Highest-risk transformers (failure probability × customers affected)" /></Tabs.Panel>
        <Tabs.Panel value="plan"><PlanTab region={region} regionName={sm.regions.find(r => r.id === region)?.name} /></Tabs.Panel>
      </Tabs>

      <CircuitDrawer id={circuit} onClose={() => set("circuit", null)} />
      <ImportModal opened={importOpen} onClose={importCtl.close} />
    </>
  );
}

type SortKey = "risk" | "mean_hi" | "pct_poor" | "mean_age" | "expected_failures";

function CircuitsTab({ region, regionName, onOpen }: { region: string | null; regionName?: string; onOpen: (id: string) => void }) {
  const { data } = useGet<CircuitHealth[]>(`/assets/circuits${region ? `?region=${region}` : ""}`);
  const routes = useRoutes();
  const [sort, setSort] = useState<SortKey>("risk");
  const [limit, setLimit] = useState(25);
  if (!data) return <Loading />;
  const rows = [...data].sort((a, b) => (sort === "mean_hi" ? a.mean_hi - b.mean_hi : (b[sort] as number) - (a[sort] as number)));
  const byId = new Map(data.map(c => [c.id, c]));
  const lines = (routes.data?.feeders ?? []).filter(f => byId.has(f.id) && f.route.length)
    .sort((a, b) => byId.get(b.id)!.mean_hi - byId.get(a.id)!.mean_hi)
    .map(f => {
      const c = byId.get(f.id)!;
      return { id: f.id, lines: f.route, color: hiColor(c.mean_hi), weight: 2 + c.pct_poor * 10,
        popup: <div><b>{c.id}</b> · {c.substation} · {c.zone}<br />{fmt(c.xfmrs)} transformers · mean age {c.mean_age} y<br />
          Health {Math.round(c.mean_hi)} · {pct(c.pct_poor)} poor/critical<br /><Button size="compact-xs" mt={4} onClick={() => onOpen(c.id)}>Open circuit</Button></div> };
    });
  return (
    <Stack>
      <Card padding="sm">
        <TerritoryMap height={420} lines={lines} />
        <Group gap="md" mt={6}>
          <Text size="xs" c="dimmed">Circuit colour = mean transformer health; thicker = larger Poor/Critical share.</Text>
          {[["#3ec46d", "≥ 70"], ["#f5a623", "55–70"], ["#f07a2e", "40–55"], ["#e0506a", "< 40"]].map(([c, l]) => (
            <Group key={l} gap={4}><div style={{ width: 10, height: 10, borderRadius: 2, background: c }} /><Text size="xs" c="dimmed">{l}</Text></Group>))}
        </Group>
      </Card>
      <Card padding={0}>
        <Group p="md" pb={0} justify="space-between">
          <Text fw={600}>Circuits {regionName && <Badge ml={6} variant="light">{regionName}</Badge>} <Text span size="sm" c="dimmed">({data.length})</Text></Text>
          <Select size="xs" w={210} value={sort} onChange={v => v && setSort(v as SortKey)} allowDeselect={false} data={[
            { value: "risk", label: "Sort: customer risk" }, { value: "mean_hi", label: "Sort: worst health" }, { value: "pct_poor", label: "Sort: % poor/critical" },
            { value: "mean_age", label: "Sort: oldest" }, { value: "expected_failures", label: "Sort: expected failures" }]} />
        </Group>
        <Table.ScrollContainer minWidth={980}>
          <Table mt="xs" highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>Circuit</Table.Th><Table.Th>Substation · zone</Table.Th><Table.Th ta="right">Customers</Table.Th>
              <Table.Th ta="right">Transformers</Table.Th><Table.Th ta="right">Mean age</Table.Th><Table.Th w={150}>Health</Table.Th>
              <Table.Th ta="right">Poor / critical</Table.Th><Table.Th ta="right">Past life</Table.Th><Table.Th ta="right">Failures / yr</Table.Th>
              <Table.Th ta="right">Risk</Table.Th><Table.Th ta="right">Backlog</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.slice(0, limit).map(c => (
              <Table.Tr key={c.id} className="row-click" onClick={() => onOpen(c.id)}>
                <Table.Td ff="monospace" fz="sm" fw={600}>{c.id}{c.critical_facility && <Tooltip label={c.critical_facility}><Badge ml={6} size="xs" color="red" variant="outline">critical</Badge></Tooltip>}</Table.Td>
                <Table.Td><Text size="sm">{c.substation ?? "—"}</Text><Text size="xs" c="dimmed">{c.zone} · {c.region}</Text></Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(c.customers)}</Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(c.xfmrs)}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.mean_age} y</Table.Td>
                <Table.Td><Group gap={6} wrap="nowrap"><Progress value={c.mean_hi} color={hiColor(c.mean_hi)} size="sm" w={70} /><Text size="sm" fw={600}>{Math.round(c.mean_hi)}</Text></Group></Table.Td>
                <Table.Td ta="right" className="tabular" c={c.pct_poor >= 0.25 ? "orange.5" : undefined}>{fmt(c.poor)} <Text span size="xs" c="dimmed">({pct(c.pct_poor)})</Text></Table.Td>
                <Table.Td ta="right" className="tabular">{pct(c.pct_over_life)}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.expected_failures.toFixed(1)}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.risk.toFixed(1)}</Table.Td>
                <Table.Td ta="right" className="tabular">{money(c.replacement_capex)}</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group p="sm" justify="space-between">
          <Text size="xs" c="dimmed">Risk = expected customer-outages a year from transformer failures (12-month failure probability × customers on each unit, doubled where a
            critical facility is on the circuit). Click a circuit for its transformers.</Text>
          {rows.length > limit && <Button size="xs" variant="subtle" onClick={() => setLimit(l => l + 50)}>Show more ({rows.length - limit})</Button>}
        </Group>
      </Card>
    </Stack>
  );
}

function SubstationsTab({ region }: { region: string | null }) {
  const { data } = useGet<SubstationAsset[]>(`/assets/substations${region ? `?region=${region}` : ""}`);
  if (!data) return <Loading />;
  return (
    <Card padding={0}>
      <Table.ScrollContainer minWidth={1100}>
        <Table highlightOnHover>
          <Table.Thead><Table.Tr><Table.Th>Unit</Table.Th><Table.Th>Region · zone</Table.Th><Table.Th ta="right">Rating</Table.Th><Table.Th ta="right">Age</Table.Th>
            <Table.Th ta="right">DGA (TDCG)</Table.Th><Table.Th ta="right">Moisture</Table.Th><Table.Th ta="right">Faults</Table.Th><Table.Th ta="right">Peak load</Table.Th>
            <Table.Th>Health</Table.Th><Table.Th ta="right">Failure / yr</Table.Th><Table.Th>What drives it</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{data.map(a => (
            <Table.Tr key={a.id}>
              <Table.Td><Text size="sm" fw={600}>{a.name}</Text><Text size="xs" c="dimmed">{a.id} · {a.manufacturer}{a.ltc ? " · LTC" : ""} · {a.circuits} circuits</Text></Table.Td>
              <Table.Td><Text size="sm">{a.region ?? "—"}</Text><Text size="xs" c="dimmed">{a.zone}</Text></Table.Td>
              <Table.Td ta="right" className="tabular">{(a.rating_kva / 1000).toFixed(1)} MVA</Table.Td>
              <Table.Td ta="right" className="tabular">{a.age} y<Text size="xs" c="dimmed">{a.install_year}</Text></Table.Td>
              <Table.Td ta="right" className="tabular">{fmt(a.dga_tdcg_ppm)} ppm</Table.Td>
              <Table.Td ta="right" className="tabular">{a.oil_moisture_ppm ?? "—"} ppm</Table.Td>
              <Table.Td ta="right" className="tabular">{a.through_faults ?? "—"}</Table.Td>
              <Table.Td ta="right" className="tabular">{a.peak_load_pct != null ? `${Math.round(a.peak_load_pct)}%` : "—"}</Table.Td>
              <Table.Td><HealthBadge hi={a.health_index} condition={a.condition} />{a.maintenance_overdue && <Badge ml={4} size="xs" color="orange" variant="outline">maint. overdue</Badge>}</Table.Td>
              <Table.Td ta="right" className="tabular">{pct(a.pof_12m, 1)}</Table.Td>
              <Table.Td><Text size="xs" c="dimmed">{a.drivers.slice(0, 2).join(" · ") || "—"}</Text></Table.Td>
            </Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Text size="xs" c="dimmed" p="sm">Dissolved-gas conditions follow IEEE C57.104 (TDCG ≤ 720 / 1,920 / 4,630 ppm). Ranked by risk: a substation unit's failure takes out every
        circuit it feeds.</Text>
    </Card>
  );
}

function AssetTable({ rows, title, showWhere }: { rows: Asset[]; title?: string; showWhere?: boolean }) {
  return (
    <Card padding={0}>
      {title && <Text fw={600} p="md" pb={0}>{title}</Text>}
      <Table.ScrollContainer minWidth={860}>
        <Table mt="xs" highlightOnHover>
          <Table.Thead><Table.Tr><Table.Th>Unit</Table.Th>{showWhere && <Table.Th>Where</Table.Th>}<Table.Th ta="right">Age</Table.Th><Table.Th ta="right">Rating</Table.Th>
            <Table.Th ta="right">Inspection</Table.Th><Table.Th ta="right">Peak load</Table.Th><Table.Th>Health</Table.Th><Table.Th ta="right">Failure / yr</Table.Th>
            <Table.Th>What drives it</Table.Th><Table.Th ta="right">Replace</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{rows.map(a => (
            <Table.Tr key={a.id}>
              <Table.Td><Text size="sm" fw={600}>{a.name}</Text><Text size="xs" c="dimmed" ff="monospace">{a.id}</Text></Table.Td>
              {showWhere && <Table.Td><Text size="sm">{a.feeder_id ?? a.substation_id}</Text><Text size="xs" c="dimmed">{a.kind === "power_transformer" ? "Substation" : "Circuit"}</Text></Table.Td>}
              <Table.Td ta="right" className="tabular">{a.age} y</Table.Td>
              <Table.Td ta="right" className="tabular">{a.rating_kva >= 1000 ? `${(a.rating_kva / 1000).toFixed(1)} MVA` : `${a.rating_kva} kVA`}</Table.Td>
              <Table.Td ta="right" className="tabular">{a.inspection_score ? `${a.inspection_score}/5` : "—"}<Text size="xs" c="dimmed">{a.last_inspection ?? ""}</Text></Table.Td>
              <Table.Td ta="right" className="tabular">{a.peak_load_pct != null ? `${Math.round(a.peak_load_pct)}%` : "—"}</Table.Td>
              <Table.Td><HealthBadge hi={a.health_index} condition={a.condition} /></Table.Td>
              <Table.Td ta="right" className="tabular">{pct(a.pof_12m, 1)}</Table.Td>
              <Table.Td><Text size="xs" c="dimmed">{a.drivers.slice(0, 2).join(" · ") || "—"}</Text></Table.Td>
              <Table.Td ta="right" className="tabular">{money(a.replacement_cost)}</Table.Td>
            </Table.Tr>))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}

const PAGE = 25;

function CircuitDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("risk");
  const { data: c } = useGet<CircuitHealthDetail>(id ? `/assets/circuits/${id}?sort=${sort}&limit=${PAGE}&offset=${(page - 1) * PAGE}` : null);
  const { event } = useCurrentEvent();
  const ev = useGet<StormEvent & { prediction: PredictionRun | null }>(id && event ? `/events/${event.id}` : null);
  const pc: PredCircuit | undefined = ev.data?.prediction?.result.circuits?.find(x => x.id === id);
  return (
    <Drawer opened={!!id} onClose={() => { setPage(1); onClose(); }} position="right" size="xl" title={<Text fw={700}>Circuit {id}</Text>}>
      {!c ? <Loading /> : (
        <Stack>
          <Text size="sm" c="dimmed">{c.substation} · {c.zone} · {c.region} region · {fmt(c.customers)} customers · {c.overhead_pct}% overhead
            {c.critical_facility && <> · <Text span c="red.4">{c.critical_facility}</Text></>}</Text>
          <SimpleGrid cols={4}>
            <Stat label="Transformers" value={fmt(c.xfmrs)} hint={`mean age ${c.mean_age} y`} />
            <Stat label="Mean health" value={Math.round(c.mean_hi)} color={c.mean_hi >= 70 ? "teal" : c.mean_hi >= 55 ? "yellow" : "red"} hint={`${pct(c.pct_over_life)} past design life`} />
            <Stat label="Poor / critical" value={fmt(c.poor)} color="orange" hint={pct(c.pct_poor)} />
            <Stat label="Failures / yr" value={c.expected_failures.toFixed(1)} color="red" hint={`backlog ${money(c.replacement_capex)}`} />
          </SimpleGrid>
          {pc && ev.data && (
            <Alert color={pc.in_path ? "red" : "blue"} icon={<IconActivityHeartbeat size={18} />} title={`In ${ev.data.name}`}>
              Predicted {fmt(pc.pred)} of {fmt(pc.customers)} customers out ({pct(pc.pct)}), back in about {Math.round(pc.eta_h)} h
              ({Math.round(pc.low_h)}–{Math.round(pc.high_h)} h).{pc.in_path && ` On the EF${pc.path_ef} damage path: plan a rebuild.`}{" "}
              {c.pct_poor >= 0.2 ? "Its older transformers raise both the outage share and the repair time." : "Its transformer fleet is in reasonable health."}
            </Alert>)}
          <Grid>
            <Grid.Col span={6}>
              <Text size="sm" fw={600} mb={6}>Age</Text>
              <BarChart h={160} data={c.age_histogram} dataKey="decade" series={[{ name: "count", label: "Transformers", color: "brand.5" }]} tickLine="none" gridAxis="y" />
            </Grid.Col>
            <Grid.Col span={6}>
              <Text size="sm" fw={600} mb={6}>Health index</Text>
              <BarChart h={160} data={c.hi_histogram} dataKey="band" series={[{ name: "count", label: "Transformers", color: "teal.5" }]} tickLine="none" gridAxis="y" />
            </Grid.Col>
          </Grid>
          <BandBar bands={c.bands} />
          {c.power_transformers.length > 0 && <>
            <Text size="sm" fw={600}>Substation {c.substation}: power transformers</Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>{c.power_transformers.map(a => (
              <Card key={a.id} withBorder padding="sm">
                <Group justify="space-between"><Text size="sm" fw={600}>{a.name}</Text><HealthBadge hi={a.health_index} condition={a.condition} /></Group>
                <Text size="xs" c="dimmed">{(a.rating_kva / 1000).toFixed(1)} MVA · {a.manufacturer} · {a.install_year} ({a.age} y){a.ltc ? " · LTC" : ""}</Text>
                <Text size="xs" mt={4}>DGA {fmt(a.dga_tdcg_ppm)} ppm · moisture {a.oil_moisture_ppm} ppm · {a.through_faults} through-faults · peak {Math.round(a.peak_load_pct ?? 0)}%</Text>
                <Text size="xs" c="dimmed" mt={4}>{a.drivers.slice(0, 3).join(" · ")}</Text>
              </Card>))}
            </SimpleGrid>
          </>}
          <Group justify="space-between">
            <Text size="sm" fw={600}>Distribution transformers</Text>
            <Select size="xs" w={170} value={sort} onChange={v => { if (v) { setSort(v); setPage(1); } }} allowDeselect={false}
              data={[{ value: "risk", label: "Highest risk first" }, { value: "health", label: "Worst health first" }, { value: "age", label: "Oldest first" }]} />
          </Group>
          <AssetTable rows={c.transformers} />
          {c.xfmrs > PAGE && <Group justify="center"><Pagination size="sm" total={Math.ceil(c.xfmrs / PAGE)} value={page} onChange={setPage} /></Group>}
        </Stack>
      )}
    </Drawer>
  );
}

function ImportModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const sample = useGet<{ csv: string; fields: string[]; density: number }>(opened ? "/admin/assets/sample" : null);
  const [csv, setCsv] = useState("");
  const [replace, setReplace] = useState(false);
  const imp = useAction((body: object) => api.post<{ added: number; updated: number; total: number }>("/admin/assets/import", body),
    { success: r => `${r.added} added, ${r.updated} updated · ${fmt(r.total)} assets on file`, invalidate: ["/assets", "/events"] });
  return (
    <Modal opened={opened} onClose={onClose} title="Import asset register" size="lg">
      <Stack>
        <Alert color="gray" icon={<IconInfoCircle size={18} />}>One row per transformer, matched by <b>id</b> (updated) or added. Health, failure probability and risk are
          recalculated on import. The sandbox register is synthetic (about one distribution transformer per {sample.data?.density ?? 10} customers).</Alert>
        <Text size="xs" c="dimmed">Columns: {sample.data?.fields.join(", ")}</Text>
        <Textarea autosize minRows={8} ff="monospace" value={csv} onChange={e => setCsv(e.currentTarget.value)}
          placeholder={sample.data?.csv ?? "id,kind,feeder_id,substation_id,install_year,..."} />
        <Group justify="space-between">
          <Group gap="xs">
            <Button size="xs" variant="subtle" onClick={() => setCsv(sample.data?.csv ?? "")}>Use example rows</Button>
            <Switch size="xs" label="Replace the sandbox register" checked={replace} onChange={e => setReplace(e.currentTarget.checked)} />
          </Group>
          <Group gap="xs">
            <Button variant="default" onClick={onClose}>Cancel</Button>
            <Button loading={imp.isPending} disabled={csv.trim().length < 10} onClick={async () => { await imp.mutateAsync({ csv, replace }); onClose(); setCsv(""); }}>Import</Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  );
}

const MARKS = [1, 5, 10, 20, 50, 100, 200];

/** Capital plan: what a budget buys in avoided customer outages, and the fleet in 5 and 10 years with and without it. */
function PlanTab({ region, regionName }: { region: string | null; regionName?: string }) {
  const [budgetM, setBudgetM] = useState(20);
  const [kind, setKind] = useState("all");
  const [debounced] = useDebouncedValue(budgetM, 350);
  const { data: p, isFetching } = useGet<ReplacementPlan>(
    `/assets/plan?budget=${debounced * 1e6}${region ? `&region=${region}` : ""}${kind !== "all" ? `&kind=${kind}` : ""}`);
  return (
    <Stack>
      <Card>
        <Grid align="center">
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Text size="sm" fw={600}>Replacement budget: {money(budgetM * 1e6)} {regionName && <Badge ml={6} variant="light">{regionName}</Badge>}</Text>
            <Slider mt="sm" mb="lg" min={1} max={200} step={1} value={budgetM} onChange={setBudgetM} label={v => money(v * 1e6)}
              marks={MARKS.map(m => ({ value: m, label: `$${m}M` }))} />
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 5 }}>
            <SegmentedControl fullWidth value={kind} onChange={setKind} data={[{ value: "all", label: "All transformers" },
              { value: "power_transformer", label: "Substation" }, { value: "dist_transformer", label: "Distribution" }]} />
          </Grid.Col>
        </Grid>
        <Text size="xs" c="dimmed">Units are ranked by customer risk removed per dollar, averaged over now, +5 and +10 years so fast-ageing units count, then funded in
          order until the budget runs out. Click a region in the table above to plan for one region.</Text>
      </Card>
      {!p ? <Loading /> : <>
        <SimpleGrid cols={{ base: 2, md: 5 }} style={{ opacity: isFetching ? 0.6 : 1 }}>
          <Stat label="Units replaced" value={fmt(p.units)} hint={`${p.by_kind.power_transformer ?? 0} substation · ${fmt(p.by_kind.dist_transformer ?? 0)} distribution`} />
          <Stat label="Spend" value={money(p.cost)} hint={`of ${money(p.budget)}`} />
          <Stat label="Customer risk removed" value={pct(p.risk_reduced_pct)} color="teal" hint="customer-outages a year from failures" />
          <Stat label="Failures avoided / yr" value={fmt(p.failures_avoided)} color="teal" hint="expected, this year" />
          <Stat label="Poor / critical replaced" value={fmt(p.poor_replaced)} color="orange" hint={`of ${fmt(p.fleet)} units in scope`} />
        </SimpleGrid>
        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card h="100%">
              <SectionTitle>What each budget buys</SectionTitle>
              <LineChart h={220} data={p.frontier.map(f => ({ budget: `$${f.budget / 1e6}M`, "Risk removed": Math.round(f.risk_reduced_pct * 100) }))}
                dataKey="budget" series={[{ name: "Risk removed", color: "teal.5" }]} unit="%" curveType="monotone" gridAxis="y" />
              <Text size="xs" c="dimmed" mt="xs">Diminishing returns: the first dollars go to the few substation units and failing transformers carrying most of the
                customer risk.</Text>
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card h="100%">
              <SectionTitle>Outlook: expected failures a year</SectionTitle>
              <BarChart h={220} data={p.projection.map(x => ({ when: x.label, "No action": x.no_action.expected_failures, "With plan": x.with_plan.expected_failures }))}
                dataKey="when" series={[{ name: "No action", color: "red.5" }, { name: "With plan", color: "teal.5" }]} gridAxis="y" valueFormatter={v => fmt(v)} />
              <Table fz="xs" mt="xs">
                <Table.Thead><Table.Tr><Table.Th /><Table.Th ta="right">Poor / critical, no action</Table.Th><Table.Th ta="right">Customer risk, no action</Table.Th>
                  <Table.Th ta="right">With plan</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{p.projection.map(x => (
                  <Table.Tr key={x.year}><Table.Td>{x.label} ({x.year})</Table.Td><Table.Td ta="right">{pct(x.no_action.pct_poor)}</Table.Td>
                    <Table.Td ta="right">{fmt(x.no_action.risk)}</Table.Td><Table.Td ta="right" c="teal.5">{fmt(x.with_plan.risk)}</Table.Td></Table.Tr>))}
                </Table.Tbody>
              </Table>
            </Card>
          </Grid.Col>
        </Grid>
        {p.by_region.length > 1 && (
          <Card padding={0}>
            <Text fw={600} p="md" pb={0}>Where the money goes</Text>
            <Table mt="xs">
              <Table.Thead><Table.Tr><Table.Th>Region</Table.Th><Table.Th ta="right">Units</Table.Th><Table.Th ta="right">Substation units</Table.Th>
                <Table.Th ta="right">Spend</Table.Th><Table.Th ta="right">Customer risk removed</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{p.by_region.map(r => (
                <Table.Tr key={r.id}><Table.Td fw={600}>{r.name}</Table.Td><Table.Td ta="right">{fmt(r.units)}</Table.Td><Table.Td ta="right">{r.power}</Table.Td>
                  <Table.Td ta="right">{money(r.cost)}</Table.Td><Table.Td ta="right">{fmt(r.risk_reduced)}</Table.Td></Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Card>)}
        <Card padding={0}>
          <Text fw={600} p="md" pb={0}>Replacement list <Text span size="sm" c="dimmed">({fmt(p.units)} units, highest risk removed first{p.units > p.items.length ? `; first ${p.items.length} shown` : ""})</Text></Text>
          <Table.ScrollContainer minWidth={900}>
            <Table mt="xs" highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>Unit</Table.Th><Table.Th>Where</Table.Th><Table.Th ta="right">Age</Table.Th><Table.Th>Health</Table.Th>
                <Table.Th>Why</Table.Th><Table.Th ta="right">Cost</Table.Th><Table.Th ta="right">Risk removed / yr</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{p.items.map(a => (
                <Table.Tr key={a.id}>
                  <Table.Td><Text size="sm" fw={600}>{a.name}</Text><Text size="xs" c="dimmed" ff="monospace">{a.id}</Text></Table.Td>
                  <Table.Td><Text size="sm">{a.where}</Text><Text size="xs" c="dimmed">{a.region}</Text></Table.Td>
                  <Table.Td ta="right">{a.age} y</Table.Td>
                  <Table.Td><HealthBadge hi={a.health_index} condition={a.condition} /></Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{a.drivers.join(" · ")}</Text></Table.Td>
                  <Table.Td ta="right">{money(a.cost)}</Table.Td>
                  <Table.Td ta="right" fw={600}>{a.risk_reduced.toFixed(1)}</Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Text size="xs" c="dimmed" p="sm">Risk removed = expected customer-outages a year the unit would cause (failure probability × customers it serves, doubled for
            critical facilities) minus a new unit's. The no-action outlook keeps today's inspection and oil results, so real deterioration would be faster.</Text>
        </Card>
      </>}
    </Stack>
  );
}
