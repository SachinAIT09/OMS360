import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Alert, Badge, Button, Card, Grid, Group, List, Modal, NumberInput, SegmentedControl, Select, SimpleGrid, Slider, Stack, Switch, Table, Tabs, Text, Textarea, Tooltip,
} from "@mantine/core";
import { BarChart, LineChart } from "@mantine/charts";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { IconBolt, IconBuildingFactory2, IconCash, IconFileUpload, IconInfoCircle, IconMap2 } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet, useGeo, useRoutes } from "../api/hooks";
import type { Asset, AssetKind, AssetSummary, CircuitHealth, HealthModel, ReplacementPlan, SubstationAsset, WorkOrder } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { WorkOrders } from "../components/AssetDetail";
import { AgeText, AssetLink, AssetTable, BandBar, HealthBadge, KIND_LABEL, KIND_PLURAL, ModelNote, hiColor } from "../components/assetUi";
import { ErrorState, Loading, PageHeader, SectionTitle, Stat } from "../components/common";
import { TerritoryMap } from "../components/TerritoryMap";
import { date, fmt, money, pct } from "../lib/format";
import { PROFILE } from "../lib/profile";

export default function AssetHealthPage() {
  const [params, setParams] = useSearchParams();
  const region = params.get("region");
  const tab = params.get("tab") ?? "circuits";
  const set = (k: string, v: string | null) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  const { can } = useAuth();
  const go = useNavigate();
  const [importOpen, importCtl] = useDisclosure(false);
  const { data: sm, isFetching, error } = useGet<AssetSummary>(`/assets/summary${region ? `?region=${region}` : ""}`);
  const all = useGet<AssetSummary>("/assets/summary");  // the region table always lists every region
  if (error || all.error) return <ErrorState error={error ?? all.error} />;
  if (!sm || !all.data) return <Loading />;
  const d = sm.distribution, p = sm.power;
  const regionName = all.data.regions.find(r => r.id === region)?.name;

  return (
    <>
      <PageHeader title="Asset health"
        description={`Age and condition of major equipment across ${PROFILE.utility}, by region, substation, circuit and unit — and how it changes storm risk.`}
        actions={<Group gap="xs">
          <Button variant="default" leftSection={<IconMap2 size={16} />} onClick={() => go(`/network${region ? `?region=${region}` : ""}`)}>Open in network explorer</Button>
          {can("assets.manage") && <Button variant="default" leftSection={<IconFileUpload size={16} />} onClick={importCtl.open}>Import asset register</Button>}
        </Group>} />
      <Group mb="md" gap="sm" wrap="wrap">
        <Select w={220} placeholder="All regions" clearable value={region} onChange={v => set("region", v)} aria-label="Region"
          data={all.data.regions.map(r => ({ value: r.id, label: `${r.name} region` }))} />
        {region && <Badge size="lg" variant="light">Showing {regionName} region</Badge>}
        <ModelNote compact />
        <Tooltip label={`Ages are whole years from the install year to ${date(sm.reference_date)}`}><Badge variant="outline" color="gray">Ages as of {date(sm.reference_date)}</Badge></Tooltip>
        {Object.entries(sm.sources).map(([k, n]) => <Badge key={k} variant="outline" color={k === "imported" ? "teal" : "gray"}>{fmt(n)} {k === "imported" ? "imported" : "sandbox (synthetic)"} records</Badge>)}
      </Group>
      <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }} mb="lg" style={{ opacity: isFetching ? 0.7 : 1 }}>
        <Stat label="Distribution transformers" value={fmt(d.units)} hint={`mean age ${d.mean_age} y · oldest ${d.oldest} y`} icon={<IconBolt size={16} />} />
        <Stat label="Poor or critical" value={fmt(sm.all.poor)} color="orange" hint={`${pct(sm.all.pct_poor)} of ${fmt(sm.all.units)} units · ${fmt(sm.all.critical)} critical`} progress={sm.all.pct_poor} />
        <Stat label="Not scored" value={fmt(sm.all.unknown)} hint="install year not recorded" />
        <Stat label="Expected failures, 12 mo" value={fmt(sm.all.expected_failures)} color="red" hint="Weibull on effective age" />
        <Stat label="Substation transformers" value={fmt(p.units)} icon={<IconBuildingFactory2 size={16} />} hint={`${p.poor} poor/critical · mean age ${p.mean_age} y`} />
        <Stat label="Replacement backlog" value={money(sm.replacement_capex)} icon={<IconCash size={16} />} color="ai" hint={`Poor + Critical units · ${sm.open_work_orders} open work orders`} />
      </SimpleGrid>

      <Grid gutter="lg" mb="lg">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card h="100%">
            <SectionTitle>Distribution transformers by age{regionName ? ` — ${regionName}` : ""}</SectionTitle>
            <BarChart h={200} data={sm.age_histogram} dataKey="decade" series={[{ name: "count", label: "Transformers", color: "brand.5" }]}
              tickLine="none" gridAxis="y" valueFormatter={v => fmt(v)} />
            <Text size="sm" fw={600} mt="md" mb={6}>Condition by equipment type</Text>
            <Stack gap="sm">{sm.by_kind.map(k => (
              <div key={k.kind}><Text size="xs" c="dimmed" mb={2}>{KIND_PLURAL[k.kind]} · {fmt(k.units)} · mean age {k.mean_age} y</Text><BandBar bands={k.bands ?? {}} /></div>))}</Stack>
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
                <Table.Tbody>{all.data.regions.map(r => (
                  <Table.Tr key={r.id} className="row-click" onClick={() => set("region", region === r.id ? null : r.id)} bg={region === r.id ? "var(--mantine-color-default-hover)" : undefined}>
                    <Table.Td fw={600}>{r.name}</Table.Td>
                    <Table.Td ta="right" className="tabular">{r.circuits}</Table.Td>
                    <Table.Td ta="right" className="tabular">{fmt(r.units)}</Table.Td>
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
            <Text size="xs" c="dimmed" p="sm">Click a region to filter every number on this page. Health index (HI) 0–100 combines age against design life with inspection, test
              and loading evidence; see the Health model tab.</Text>
          </Card>
        </Grid.Col>
      </Grid>

      <Tabs value={tab} onChange={v => set("tab", v === "circuits" ? null : v)} keepMounted={false}>
        <Tabs.List mb="md" style={{ overflowX: "auto", flexWrap: "nowrap" }}>
          <Tabs.Tab value="circuits">Circuits</Tabs.Tab>
          <Tabs.Tab value="substations">Substation transformers</Tabs.Tab>
          <Tabs.Tab value="types">By equipment type</Tabs.Tab>
          <Tabs.Tab value="plan">Replacement plan</Tabs.Tab>
          <Tabs.Tab value="workorders">Work orders</Tabs.Tab>
          <Tabs.Tab value="model">Health model</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="circuits"><CircuitsTab region={region} regionName={regionName} /></Tabs.Panel>
        <Tabs.Panel value="substations"><SubstationsTab region={region} /></Tabs.Panel>
        <Tabs.Panel value="types"><TypesTab region={region} /></Tabs.Panel>
        <Tabs.Panel value="plan"><PlanTab region={region} regionName={regionName} /></Tabs.Panel>
        <Tabs.Panel value="workorders"><WorkOrdersTab region={region} /></Tabs.Panel>
        <Tabs.Panel value="model"><ModelTab /></Tabs.Panel>
      </Tabs>
      <ImportModal opened={importOpen} onClose={importCtl.close} />
    </>
  );
}

type SortKey = "risk_all" | "mean_hi" | "pct_poor" | "mean_age" | "expected_failures";

function CircuitsTab({ region, regionName }: { region: string | null; regionName?: string }) {
  const { data, error } = useGet<CircuitHealth[]>(`/assets/circuits${region ? `?region=${region}` : ""}`);
  const routes = useRoutes();
  const geo = useGeo();
  const go = useNavigate();
  const [sort, setSort] = useState<SortKey>("risk_all");
  const [limit, setLimit] = useState(25);
  if (error) return <ErrorState error={error} />;
  if (!data) return <Loading />;
  const open = (c: CircuitHealth) => go(`/network?region=${c.region_id ?? ""}&sub=${c.substation_id ?? ""}&circuit=${c.id}`);
  const rows = [...data].sort((a, b) => (sort === "mean_hi" ? a.mean_hi - b.mean_hi : (b[sort] as number) - (a[sort] as number)));
  const byId = new Map(data.map(c => [c.id, c]));
  const lines = (routes.data?.feeders ?? []).filter(f => byId.has(f.id) && f.route.length)
    .sort((a, b) => byId.get(b.id)!.mean_hi - byId.get(a.id)!.mean_hi)
    .map(f => {
      const c = byId.get(f.id)!;
      return { id: f.id, lines: f.route, color: hiColor(c.mean_hi), weight: 2 + c.pct_poor * 10, onClick: () => open(c),
        tooltip: `${c.id} · ${c.substation} · health ${Math.round(c.mean_hi)} · ${pct(c.pct_poor)} poor — click to open` };
    });
  const hull = region ? geo.data?.regions.find(r => r.id === region)?.hull : geo.data?.state?.rings[0];
  return (
    <Stack>
      <Card padding="sm">
        <TerritoryMap height={420} lines={lines} outline={geo.data?.state?.rings} fit={hull ?? null} />
        <Group gap="md" mt={6}>
          <Text size="xs" c="dimmed">Circuit colour = mean transformer health; thicker = larger Poor/Critical share. Click a circuit to open it.</Text>
          {[["#3ec46d", "≥ 70"], ["#f5a623", "55–70"], ["#f07a2e", "40–55"], ["#e0506a", "< 40"]].map(([c, l]) => (
            <Group key={l} gap={4}><div style={{ width: 10, height: 10, borderRadius: 2, background: c }} /><Text size="xs" c="dimmed">{l}</Text></Group>))}
        </Group>
      </Card>
      <Card padding={0}>
        <Group p="md" pb={0} justify="space-between">
          <Text fw={600}>Circuits {regionName && <Badge ml={6} variant="light">{regionName}</Badge>} <Text span size="sm" c="dimmed">({data.length})</Text></Text>
          <Select size="xs" w={210} value={sort} onChange={v => v && setSort(v as SortKey)} allowDeselect={false} aria-label="Sort circuits" data={[
            { value: "risk_all", label: "Sort: customer risk" }, { value: "mean_hi", label: "Sort: worst health" }, { value: "pct_poor", label: "Sort: % poor/critical" },
            { value: "mean_age", label: "Sort: oldest" }, { value: "expected_failures", label: "Sort: expected failures" }]} />
        </Group>
        <Table.ScrollContainer minWidth={1040}>
          <Table mt="xs" highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>Circuit</Table.Th><Table.Th>Substation · zone</Table.Th><Table.Th ta="right">Customers</Table.Th>
              <Table.Th ta="right">Transformers</Table.Th><Table.Th ta="right">Mean age</Table.Th><Table.Th w={150}>Health</Table.Th>
              <Table.Th ta="right">Poor / critical</Table.Th><Table.Th ta="right">Poles poor</Table.Th><Table.Th ta="right">Switchgear poor</Table.Th>
              <Table.Th ta="right">Risk</Table.Th><Table.Th ta="right">Backlog</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.slice(0, limit).map(c => (
              <Table.Tr key={c.id} className="row-click" onClick={() => open(c)}>
                <Table.Td ff="monospace" fz="sm" fw={600}>{c.id}{c.critical_facility && <Tooltip label={c.critical_facility}><Badge ml={6} size="xs" color="red" variant="outline">critical</Badge></Tooltip>}</Table.Td>
                <Table.Td><Text size="sm">{c.substation ?? "—"}</Text><Text size="xs" c="dimmed">{c.zone} · {c.region}</Text></Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(c.customers)}</Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(c.units)}{c.unknown > 0 && <Text size="xs" c="dimmed">{c.unknown} unknown age</Text>}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.mean_age} y</Table.Td>
                <Table.Td><Group gap={6} wrap="nowrap"><div style={{ width: 70, height: 6, borderRadius: 3, background: "var(--mantine-color-default-border)" }}>
                  <div style={{ width: `${c.mean_hi}%`, height: 6, borderRadius: 3, background: hiColor(c.mean_hi) }} /></div><Text size="sm" fw={600}>{Math.round(c.mean_hi)}</Text></Group></Table.Td>
                <Table.Td ta="right" className="tabular" c={c.pct_poor >= 0.25 ? "orange.5" : undefined}>{fmt(c.poor)} <Text span size="xs" c="dimmed">({pct(c.pct_poor)})</Text></Table.Td>
                <Table.Td ta="right" className="tabular">{c.poles_poor}/{c.poles}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.switchgear_poor}/{c.switchgear}</Table.Td>
                <Table.Td ta="right" className="tabular">{c.risk_all.toFixed(1)}</Table.Td>
                <Table.Td ta="right" className="tabular">{money(c.replacement_capex)}</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group p="sm" justify="space-between">
          <Text size="xs" c="dimmed">Risk = expected customer-outages a year from equipment failures on the circuit (12-month failure probability × customers each unit serves,
            doubled where a critical facility is on the circuit).</Text>
          {rows.length > limit && <Button size="xs" variant="subtle" onClick={() => setLimit(l => l + 50)}>Show more ({rows.length - limit})</Button>}
        </Group>
      </Card>
    </Stack>
  );
}

function SubstationsTab({ region }: { region: string | null }) {
  const { data } = useGet<SubstationAsset[]>(`/assets/substations${region ? `?region=${region}` : ""}`);
  const go = useNavigate();
  if (!data) return <Loading />;
  return (
    <Card padding={0}>
      <Table.ScrollContainer minWidth={1100}>
        <Table highlightOnHover>
          <Table.Thead><Table.Tr><Table.Th>Unit</Table.Th><Table.Th>Region · zone</Table.Th><Table.Th ta="right">Rating</Table.Th><Table.Th>Age</Table.Th>
            <Table.Th ta="right">DGA (TDCG)</Table.Th><Table.Th ta="right">Moisture</Table.Th><Table.Th ta="right">Faults</Table.Th><Table.Th ta="right">Peak load</Table.Th>
            <Table.Th>Health</Table.Th><Table.Th ta="right">Failure / yr</Table.Th><Table.Th>What drives it</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{data.map(a => (
            <Table.Tr key={a.id} className="row-click" onClick={() => go(`/asset/${encodeURIComponent(a.id)}`)}>
              <Table.Td><Text size="sm" fw={600}>{a.name}</Text><Group gap={4}><AssetLink id={a.id} /><Text size="xs" c="dimmed">{a.manufacturer}{a.ltc ? " · LTC" : ""} · {a.circuits} circuits</Text></Group></Table.Td>
              <Table.Td><Text size="sm">{a.region ?? "—"}</Text><Text size="xs" c="dimmed">{a.zone}</Text></Table.Td>
              <Table.Td ta="right" className="tabular">{(a.rating_kva / 1000).toFixed(1)} MVA</Table.Td>
              <Table.Td><AgeText a={a} /></Table.Td>
              <Table.Td ta="right" className="tabular">{a.dga_tdcg_ppm != null ? `${fmt(a.dga_tdcg_ppm)} ppm` : <Text span size="xs" c="dimmed">no test</Text>}</Table.Td>
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

const TYPE_ORDER: AssetKind[] = ["pole", "recloser", "breaker", "dist_transformer", "power_transformer"];

function TypesTab({ region }: { region: string | null }) {
  const [kind, setKind] = useState<AssetKind>("pole");
  const { data } = useGet<Asset[]>(`/assets/top?n=50&kind=${kind}${region ? `&region=${region}` : ""}`);
  return (
    <Stack>
      <SegmentedControl value={kind} onChange={v => setKind(v as AssetKind)} data={TYPE_ORDER.map(k => ({ value: k, label: KIND_PLURAL[k] }))} />
      <Text size="sm" c="dimmed">{{ pole: "Wood, steel and concrete poles: remaining ground-line strength (NESC replacement below 67%), age and inspection.",
        recloser: "Line reclosers: operations against rating, timing / contact-resistance test results, interrupter type and age.",
        breaker: "Feeder breakers at substations: operations, test results, oil interrupters over 35 years.",
        dist_transformer: "Distribution transformers: age, inspection, loading.", power_transformer: "Substation transformers: age, dissolved gas, moisture, faults, maintenance." }[kind]}</Text>
      {!data ? <Loading /> : <AssetTable rows={data} showWhere title={`Highest-risk ${KIND_PLURAL[kind].toLowerCase()}`} />}
    </Stack>
  );
}

function WorkOrdersTab({ region }: { region: string | null }) {
  const [status, setStatus] = useState("open,scheduled");
  const { data } = useGet<WorkOrder[]>(`/work-orders?status=${status}${region ? `&region=${region}` : ""}`);
  return (
    <Stack>
      <SegmentedControl w={360} value={status} onChange={setStatus} data={[{ value: "open,scheduled", label: "Open" }, { value: "done", label: "Done" },
        { value: "open,scheduled,done,cancelled", label: "All" }]} />
      {!data ? <Loading /> : <WorkOrders rows={data} showAsset />}
      <Text size="xs" c="dimmed">Create work orders from a unit's recommended actions (open any unit from the tables or the network explorer).</Text>
    </Stack>
  );
}

function ModelTab() {
  const { data } = useGet<HealthModel>("/assets/model");
  const { can } = useAuth();
  const [w, setW] = useState<Record<string, number> | null>(null);
  const save = useAction((weights: Record<string, number>) => api.put<HealthModel>("/admin/assets/model", { weights }),
    { success: "Weights saved — every unit re-scored", invalidate: ["/assets", "/events", "/network"] });
  if (!data) return <Loading />;
  const vals = w ?? data.weights;
  return (
    <Grid gutter="lg">
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <Card>
          <SectionTitle right={<Badge color="yellow" variant="light">{data.status}</Badge>}>How the health score works</SectionTitle>
          <List size="sm" spacing={4}>{data.notes.map(n => <List.Item key={n}>{n}</List.Item>)}</List>
          <Text size="sm" fw={600} mt="md">Design life used for age</Text>
          <Group gap="xs" mt={4}>{Object.entries(data.design_life).map(([k, v]) => <Badge key={k} variant="outline" color="gray">{k}: {v} y</Badge>)}</Group>
          <Text size="sm" fw={600} mt="md">Failure probability (Weibull)</Text>
          <Group gap="xs" mt={4}>{Object.entries(data.weibull).map(([k, v]) => <Badge key={k} variant="outline" color="gray">{k}: η {v.eta_y} y, β {v.beta}</Badge>)}</Group>
          <Alert mt="md" color="gray" icon={<IconInfoCircle size={18} />} p="xs">
            <Text size="xs">Each penalty (points off 100) is multiplied by its weight. Weights and band thresholds are a starting point for the utility's asset-management team to
              calibrate against its own failure records; changing them re-scores every unit and feeds the storm predictions and replacement plan.</Text></Alert>
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <Card>
          <SectionTitle>Weights</SectionTitle>
          <Stack gap="xs">{Object.keys(data.defaults).map(k => (
            <NumberInput key={k} label={data.labels[k]} size="xs" step={k.startsWith("band_") || k === "age_weight" ? 1 : 0.1} decimalScale={2}
              min={k === "age_weight" ? 5 : k.startsWith("band_") ? 1 : 0} max={k === "age_weight" || k.startsWith("band_") ? 99 : 5}
              value={vals[k]} disabled={!can("assets.manage")} onChange={v => setW({ ...vals, [k]: Number(v) })}
              rightSection={vals[k] !== data.defaults[k] ? <Tooltip label={`Default ${data.defaults[k]}`}><Text size="xs" c="yellow.6">●</Text></Tooltip> : undefined} />))}
          </Stack>
          {can("assets.manage") ? (
            <Group justify="flex-end" mt="md">
              <Button variant="default" size="xs" onClick={() => setW({ ...data.defaults })}>Reset to defaults</Button>
              <Button size="xs" loading={save.isPending} disabled={!w} onClick={async () => { await save.mutateAsync(vals); setW(null); }}>Save and re-score</Button>
            </Group>) : <Text size="xs" c="dimmed" mt="sm">Only asset managers can change the weights.</Text>}
        </Card>
      </Grid.Col>
    </Grid>
  );
}

const MARKS = [1, 5, 10, 20, 50, 100, 200];

/** Capital plan: what a budget buys in avoided customer outages, and the fleet in 5 and 10 years with and without it. */
function PlanTab({ region, regionName }: { region: string | null; regionName?: string }) {
  const [budgetM, setBudgetM] = useState(20);
  const [kind, setKind] = useState("all");
  const [debounced] = useDebouncedValue(budgetM, 350);
  const go = useNavigate();
  const { data: p, isFetching } = useGet<ReplacementPlan>(
    `/assets/plan?budget=${debounced * 1e6}${region ? `&region=${region}` : ""}${kind !== "all" ? `&kind=${kind}` : ""}`);
  return (
    <Stack>
      <Card>
        <Grid align="center">
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Text size="sm" fw={600}>Replacement budget: {money(budgetM * 1e6)} {regionName && <Badge ml={6} variant="light">{regionName}</Badge>}</Text>
            <Slider mt="sm" mb="lg" min={1} max={200} step={1} value={budgetM} onChange={setBudgetM} label={v => money(v * 1e6)} aria-label="Replacement budget"
              marks={MARKS.map(m => ({ value: m, label: `$${m}M` }))} />
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Select value={kind} onChange={v => v && setKind(v)} allowDeselect={false} aria-label="Equipment type"
              data={[{ value: "all", label: "All equipment types" }, ...TYPE_ORDER.map(k => ({ value: k, label: KIND_PLURAL[k] }))]} />
          </Grid.Col>
        </Grid>
        <Text size="xs" c="dimmed">Units are ranked by customer risk removed per dollar, averaged over now, +5 and +10 years so fast-ageing units count, then funded in
          order until the budget runs out. Pick a region at the top of the page to plan for one region.</Text>
      </Card>
      {!p ? <Loading /> : !p.fleet ? <Alert color="gray">No units in scope.</Alert> : <>
        <SimpleGrid cols={{ base: 2, md: 5 }} style={{ opacity: isFetching ? 0.6 : 1 }}>
          <Stat label="Units replaced" value={fmt(p.units)} hint={Object.entries(p.by_kind).filter(([, n]) => n).map(([k, n]) => `${fmt(n)} ${KIND_LABEL[k as AssetKind].toLowerCase()}`).join(" · ") || "—"} />
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
              <Text size="xs" c="dimmed" mt="xs">Diminishing returns: the first dollars go to the few substation units and failing equipment carrying most of the customer risk.</Text>
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
                <Table.Tr key={a.id} className="row-click" onClick={() => go(`/asset/${encodeURIComponent(a.id)}`)}>
                  <Table.Td><Text size="sm" fw={600}>{a.name}</Text><AssetLink id={a.id} /></Table.Td>
                  <Table.Td><Text size="sm">{a.where}</Text><Text size="xs" c="dimmed">{a.region}</Text></Table.Td>
                  <Table.Td ta="right">{a.age != null ? `${a.age} y` : <Text span size="xs" c="dimmed">unknown</Text>}</Table.Td>
                  <Table.Td><HealthBadge hi={a.health_index} condition={a.condition} /></Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{a.drivers.join(" · ")}</Text></Table.Td>
                  <Table.Td ta="right">{money(a.cost)}</Table.Td>
                  <Table.Td ta="right" fw={600}>{a.risk_reduced.toFixed(1)}</Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Text size="xs" c="dimmed" p="sm">Risk removed = expected customer-outages a year the unit would cause (failure probability × customers it serves, doubled for
            critical facilities) minus a new unit's. The no-action outlook keeps today's inspection and test results, so real deterioration would be faster.</Text>
        </Card>
      </>}
    </Stack>
  );
}

function ImportModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const sample = useGet<{ csv: string; fields: string[]; density: number }>(opened ? "/admin/assets/sample" : null);
  const [csv, setCsv] = useState("");
  const [replace, setReplace] = useState(false);
  const imp = useAction((body: object) => api.post<{ added: number; updated: number; total: number; missing_install_year: number }>("/admin/assets/import", body),
    { success: r => `${r.added} added, ${r.updated} updated · ${fmt(r.total)} units on file${r.missing_install_year ? ` · ${r.missing_install_year} without an install year (shown as Unknown)` : ""}`,
      invalidate: ["/assets", "/events", "/network"] });
  return (
    <Modal opened={opened} onClose={onClose} title="Import asset register" size="lg">
      <Stack>
        <Alert color="gray" icon={<IconInfoCircle size={18} />}>One row per unit — transformers, breakers, reclosers or poles — matched by <b>id</b> (updated) or added.
          Leave install_year or the inspection blank when unknown: those units are shown as Unknown rather than guessed. Health, failure probability and risk are
          recalculated on import. The sandbox register is synthetic (about one distribution transformer per {sample.data?.density ?? 10} customers).</Alert>
        <Text size="xs" c="dimmed">Columns: {sample.data?.fields.join(", ")}</Text>
        <Textarea autosize minRows={8} ff="monospace" value={csv} onChange={e => setCsv(e.currentTarget.value)} aria-label="CSV rows"
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
