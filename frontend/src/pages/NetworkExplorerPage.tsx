/* Network explorer: drill from the whole territory to a region, a substation, a circuit and a single unit. The map, the side
   panel, the breadcrumbs and the URL (?region=&sub=&circuit=&asset=) always describe the same selection. */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CircleMarker, Tooltip as LTooltip } from "react-leaflet";
import {
  Alert, Anchor, Badge, Breadcrumbs, Button, Card, Chip, Drawer, Grid, Group, Pagination, ScrollArea, SegmentedControl, SimpleGrid, Stack, Table, Text, Tooltip,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { IconArrowUp, IconExternalLink, IconRefresh } from "@tabler/icons-react";
import { useGet, useGeo, useReference, useRoutes } from "../api/hooks";
import type {
  AssetKind, AssetMarker, AssetSummary, CircuitHealth, CircuitHealthDetail, Outage, Page, PredCircuit, PredictionRun, StormEvent, StormImpact,
  SubstationDetail, SubstationRollup,
} from "../api/types";
import { useCurrentEvent } from "../auth/EventContext";
import { AssetDetailView } from "../components/AssetDetail";
import { AgeText, CONDITION_HEX, HealthBadge, KIND_LABEL, KIND_PLURAL, ModelNote, hiColor } from "../components/assetUi";
import { Empty, ErrorState, Loading, PageHeader, Stat } from "../components/common";
import { EF_COLOR, TerritoryMap, type MapArea, type MapLine, type MapPin } from "../components/TerritoryMap";
import { fmt, money, pct, sevColor } from "../lib/format";
import { PROFILE } from "../lib/profile";

type Layer = "outline" | "regions" | "storm" | "circuits" | "substations" | "assets" | "outages" | "facilities";
const LAYERS: { value: Layer; label: string }[] = [
  { value: "outline", label: "State outline" }, { value: "regions", label: "Regions" }, { value: "storm", label: "Storm paths" },
  { value: "circuits", label: "Circuits" }, { value: "substations", label: "Substations" }, { value: "assets", label: "Equipment" },
  { value: "outages", label: "Open outages" }, { value: "facilities", label: "Critical facilities" },
];
const ASSET_RADIUS: Record<AssetKind, number> = { power_transformer: 8, breaker: 6, recloser: 6, dist_transformer: 4, pole: 2.5 };
const PAGE = 20;

export default function NetworkExplorerPage() {
  const [params, setParams] = useSearchParams();
  const region = params.get("region") || null;
  const sub = params.get("sub") || null;
  const circuit = params.get("circuit") || null;
  const asset = params.get("asset") || null;
  const level = circuit ? "circuit" : sub ? "substation" : region ? "region" : "state";
  /** Moving the selection always clears everything below it, so no stale circuit or unit survives a region change. */
  const select = (next: { region?: string | null; sub?: string | null; circuit?: string | null; asset?: string | null }) => {
    const p = new URLSearchParams();
    const r = next.region !== undefined ? next.region : region;
    const s = next.sub !== undefined ? next.sub : next.region !== undefined ? null : sub;
    const c = next.circuit !== undefined ? next.circuit : next.region !== undefined || next.sub !== undefined ? null : circuit;
    const a = next.asset !== undefined ? next.asset : null;
    if (r) p.set("region", r);
    if (s) p.set("sub", s);
    if (c) p.set("circuit", c);
    if (a) p.set("asset", a);
    setParams(p);
  };
  const up = () => select(circuit ? { circuit: null } : sub ? { sub: null } : { region: null });

  const [layers, setLayers] = useState<string[]>(["outline", "regions", "storm", "circuits", "substations", "assets", "outages"]);
  const [colorBy, setColorBy] = useState<"health" | "storm">("health");
  const on = (l: Layer) => layers.includes(l);
  const wide = useMediaQuery("(min-width: 62em)");

  const geo = useGeo();
  const routes = useRoutes();
  const ref = useReference();
  const { event } = useCurrentEvent();
  const detail = useGet<StormEvent & { prediction: PredictionRun | null }>(event ? `/events/${event.id}` : null);
  const impact = useGet<StormImpact>(event ? `/events/${event.id}/impact` : null);
  const summary = useGet<AssetSummary>(`/assets/summary${region ? `?region=${region}` : ""}`);
  const circuits = useGet<CircuitHealth[]>(`/assets/circuits${region ? `?region=${region}` : ""}`);
  const subs = useGet<SubstationRollup[]>(`/network/substations${region ? `?region=${region}` : ""}`);
  const subDetail = useGet<SubstationDetail>(sub ? `/network/substations/${sub}` : null);
  const markers = useGet<AssetMarker[]>(circuit ? `/assets/circuits/${circuit}/markers` : null);
  const outages = useGet<Page<Outage>>(event ? `/outages?event_id=${event.id}&open_only=true&size=500${circuit ? `&feeder=${circuit}` : ""}` : null);

  const pred = detail.data?.prediction?.result;
  const predBy = useMemo(() => new Map((pred?.circuits ?? []).map(c => [c.id, c])), [pred]);
  const healthBy = useMemo(() => new Map((circuits.data ?? []).map(c => [c.id, c])), [circuits.data]);
  const routeBy = useMemo(() => new Map((routes.data?.feeders ?? []).map(f => [f.id, f])), [routes.data]);
  const scopeIds = useMemo(() => {
    if (circuit) return new Set([circuit]);
    if (sub) return new Set((circuits.data ?? []).filter(c => c.substation_id === sub).map(c => c.id));
    return new Set((circuits.data ?? []).map(c => c.id));
  }, [circuit, sub, circuits.data]);
  // A link may name only a circuit or a substation (search, assistant): fill in its parents so the breadcrumbs are complete.
  useEffect(() => {
    const c = circuit ? healthBy.get(circuit) : undefined;
    const sx = sub ? (subs.data ?? []).find(x => x.id === sub) : undefined;
    const r = c?.region_id ?? sx?.region_id ?? null, sb = c?.substation_id ?? null;
    if ((c && (r !== region || sb !== sub)) || (!c && sx && r && r !== region)) {
      const p = new URLSearchParams(params);
      if (r) p.set("region", r);
      if (sb) p.set("sub", sb);
      setParams(p, { replace: true });
    }
  }, [circuit, sub, region, healthBy, subs.data]);  // eslint-disable-line react-hooks/exhaustive-deps
  const regionName = summary.data?.regions.find(r => r.id === region)?.name ?? geo.data?.regions.find(r => r.id === region)?.name ?? region;
  const subName = subDetail.data?.name ?? sub;

  // ---- map
  const fit: [number, number][] | null = useMemo(() => {
    const pts = (ids: Iterable<string>) => [...ids].flatMap(id => (routeBy.get(id)?.route ?? []).flat()) as [number, number][];
    if (circuit) return pts([circuit]);
    if (sub) return pts(scopeIds);
    if (region) return geo.data?.regions.find(r => r.id === region)?.hull ?? pts(scopeIds);
    return geo.data?.state?.rings[0] ?? null;
  }, [circuit, sub, region, scopeIds, routeBy, geo.data]);

  const regionStats = new Map((summary.data?.regions ?? []).map(r => [r.id, r]));
  const hitBy = new Map((impact.data?.regions_affected ?? []).map(r => [r.id, r]));
  const areas: MapArea[] = on("regions") ? (geo.data?.regions ?? []).map(r => {
    const st = regionStats.get(r.id), hit = hitBy.get(r.id);
    const color = colorBy === "storm" ? (hit?.circuits_hit ? "#e0506a" : hit?.pred ? "#f5a623" : "#3ec46d") : hiColor(st?.mean_hi);
    return { id: r.id, name: r.name, ring: r.hull, color, selected: region === r.id, dimmed: !!region && region !== r.id, onClick: () => select({ region: r.id }),
      label: <span><b>{r.name}</b>{st && <> · mean health {Math.round(st.mean_hi)} · {pct(st.pct_poor)} poor</>}{hit?.circuits_hit ? <> · {hit.circuits_hit} circuits in storm path</> : null}<br />approximate service area — click to open</span> };
  }) : [];

  const lines: MapLine[] = on("circuits") ? [...scopeIds].concat(circuit && sub ? (circuits.data ?? []).filter(c => c.substation_id === sub && c.id !== circuit).map(c => c.id) : [])
    .flatMap(id => {
      const f = routeBy.get(id), h = healthBy.get(id), p: PredCircuit | undefined = predBy.get(id);
      if (!f?.route.length) return [];
      const sibling = !!circuit && id !== circuit;
      const color = colorBy === "storm" ? (p ? (p.in_path ? "#e0506a" : sevColor(p.pct)) : "#8a9aa5") : hiColor(h?.mean_hi);
      return [{ id, lines: f.route, color, weight: sibling ? 1.5 : id === circuit ? 5 : colorBy === "storm" && p?.in_path ? 4 : 2.5, opacity: sibling ? 0.4 : 0.9,
        tooltip: `${id} · ${h?.zone ?? ""} · health ${h ? Math.round(h.mean_hi) : "—"}${p ? ` · ${pct(p.pct)} predicted out${p.in_path ? " · in damage path" : ""}` : ""}`,
        onClick: () => select({ region: h?.region_id ?? region, sub: h?.substation_id ?? sub, circuit: id }), dashed: f.source === "synthetic" && id === circuit }];
    }) : [];

  const subPins: MapPin[] = on("substations") ? (subs.data ?? []).filter(x => !sub || x.id === sub).map(x => ({
    id: `s-${x.id}`, lat: x.lat, lng: x.lng, color: hiColor(x.worst_hi), onClick: () => select({ region: x.region_id, sub: x.id }),
  })) : [];
  const outagePins: MapPin[] = on("outages") ? (outages.data?.items ?? []).filter(o => circuit || scopeIds.has(o.feeder_id)).slice(0, 400).map(o => ({
    id: `o-${o.id}`, lat: o.lat, lng: o.lng, color: "#ff3b6b",
    popup: <div><b>{o.number}</b> · {o.status}<br />{o.feeder_id} · {fmt(o.customers)} customers<br />{o.damage} · {o.cause}{o.asset_id && <><br />Unit: <Link to={`/asset/${o.asset_id}`}>{o.asset_id}</Link></>}</div>,
  })) : [];

  return (
    <>
      <PageHeader title="Network explorer"
        description={`Drill from ${PROFILE.state || "the territory"} to a region, substation, circuit and unit — equipment health and the current storm on one map.`}
        actions={<Group gap="xs"><ModelNote compact /><Badge variant="light" color="yellow">Simulation — synthetic network & storm data</Badge></Group>} />
      <Group justify="space-between" mb="sm" wrap="wrap" gap="xs">
        <Breadcrumbs separator="›">
          <Anchor component="button" onClick={() => select({ region: null })} fw={level === "state" ? 700 : 400}>{PROFILE.state || "Territory"}</Anchor>
          {region && <Anchor component="button" onClick={() => select({ region, sub: null })} fw={level === "region" ? 700 : 400}>{regionName} region</Anchor>}
          {sub && <Anchor component="button" onClick={() => select({ region, sub, circuit: null })} fw={level === "substation" ? 700 : 400}>{subName}</Anchor>}
          {circuit && <Text fw={700} ff="monospace">{circuit}</Text>}
        </Breadcrumbs>
        <Group gap="xs">
          {level !== "state" && <Button size="xs" variant="default" leftSection={<IconArrowUp size={14} />} onClick={up}>Up a level</Button>}
          {level !== "state" && <Button size="xs" variant="subtle" leftSection={<IconRefresh size={14} />} onClick={() => select({ region: null })}>Whole territory</Button>}
        </Group>
      </Group>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card padding="sm">
            <Group justify="space-between" mb={6} wrap="wrap" gap={6}>
              <Chip.Group multiple value={layers} onChange={setLayers}>
                <Group gap={4}>{LAYERS.filter(l => l.value !== "assets" || circuit).map(l => <Chip key={l.value} value={l.value} size="xs" variant="outline">{l.label}</Chip>)}</Group>
              </Chip.Group>
              <SegmentedControl size="xs" value={colorBy} onChange={v => setColorBy(v as typeof colorBy)}
                data={[{ value: "health", label: "Colour: equipment health" }, { value: "storm", label: "Colour: storm impact" }]} />
            </Group>
            <TerritoryMap height={wide ? 620 : 420} scrollZoom fit={fit} outline={on("outline") ? geo.data?.state?.rings : null} areas={areas}
              lines={lines} pins={[...subPins, ...outagePins]} track={on("storm") ? detail.data?.track : null}
              facilities={on("facilities") ? ref.data?.facilities.filter(f => !region || scopeIds.has(f.feeder_id)) : undefined}>
              {circuit && on("assets") && (markers.data ?? []).map(m => (
                <CircleMarker key={m.id} center={[m.lat, m.lng]} radius={ASSET_RADIUS[m.kind]} eventHandlers={{ click: () => select({ region, sub, circuit, asset: m.id }) }}
                  pathOptions={{ color: m.status === "damaged" ? "#000" : CONDITION_HEX[m.condition], weight: m.status === "damaged" ? 3 : 1,
                    fillColor: CONDITION_HEX[m.condition], fillOpacity: 0.85 }}>
                  <LTooltip>{m.id} · {KIND_LABEL[m.kind]} · {m.health_index != null ? `HI ${Math.round(m.health_index)}` : "health unknown"}{m.status === "damaged" ? " · DAMAGE CONFIRMED" : ""}</LTooltip>
                </CircleMarker>))}
            </TerritoryMap>
            <MapKey colorBy={colorBy} circuit={!!circuit} storm={!!detail.data?.track?.length} />
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <ScrollArea.Autosize mah={wide ? 700 : undefined} type="auto">
            {(summary.error || circuits.error) && <ErrorState error={summary.error ?? circuits.error} />}
            {region && geo.data && !geo.data.regions.some(r => r.id === region) && (
              <Alert color="orange" mb="md" title="Region not found">There is no region "{region}" in this territory.{" "}
                <Anchor component="button" onClick={() => select({ region: null })}>Show the whole territory</Anchor></Alert>)}
            {circuit && circuits.data && !healthBy.has(circuit) && (
              <Alert color="orange" mb="md" title="Circuit not found">There is no circuit "{circuit}" with equipment records.{" "}
                <Anchor component="button" onClick={() => select({ circuit: null })}>Go up a level</Anchor></Alert>)}
            {sub && subDetail.error && <Alert color="orange" mb="md" title="Substation not found">{subDetail.error.message}</Alert>}
            {level === "state" && <StatePanel summary={summary.data} impact={impact.data} event={event} onRegion={id => select({ region: id })} />}
            {level === "region" && <RegionPanel summary={summary.data} subs={subs.data} circuits={circuits.data} predBy={predBy}
              onSub={id => select({ region, sub: id })} onCircuit={c => select({ region, sub: c.substation_id, circuit: c.id })} />}
            {level === "substation" && <SubstationPanel d={subDetail.data} failed={!!subDetail.error} predBy={predBy} onCircuit={id => select({ region, sub, circuit: id })}
              onAsset={id => select({ region, sub, asset: id })} />}
            {level === "circuit" && circuit && <CircuitPanel key={circuit} id={circuit} pred={predBy.get(circuit)} outages={(outages.data?.items ?? []).filter(o => o.feeder_id === circuit)}
              event={detail.data} onAsset={id => select({ region, sub, circuit, asset: id })} />}
          </ScrollArea.Autosize>
        </Grid.Col>
      </Grid>

      <Drawer opened={!!asset} onClose={() => select({ region, sub, circuit, asset: null })} position="right" size="xl"
        closeButtonProps={{ "aria-label": "Close unit details" }}
        title={<Group gap="xs"><Text fw={700}>Unit {asset}</Text>{asset && <Anchor component={Link} to={`/asset/${encodeURIComponent(asset)}`} fz="sm">
          Open full record <IconExternalLink size={12} /></Anchor>}</Group>}>
        {asset && <AssetDetailView id={asset} compact />}
      </Drawer>
    </>
  );
}

function MapKey({ colorBy, circuit, storm }: { colorBy: "health" | "storm"; circuit: boolean; storm: boolean }) {
  const sw = (c: string, l: string, round = false) => (
    <Group key={l} gap={4} wrap="nowrap"><div style={{ width: 10, height: 10, borderRadius: round ? 5 : 2, background: c }} /><Text size="xs" c="dimmed">{l}</Text></Group>);
  return (
    <Stack gap={4} mt={8}>
      <Group gap="md">
        <Text size="xs" fw={600}>{colorBy === "health" ? "Circuits & regions: mean transformer health" : "Circuits: predicted share out"}</Text>
        {colorBy === "health"
          ? [["#3ec46d", "≥ 70"], ["#f5a623", "55–70"], ["#f07a2e", "40–55"], ["#e0506a", "< 40"], ["#8a9aa5", "unknown"]].map(([c, l]) => sw(c, l))
          : [["#3ec46d", "< 8%"], ["#f5a623", "8–20%"], ["#f07a2e", "20–40%"], ["#e0506a", "> 40% or in damage path"], ["#8a9aa5", "no prediction"]].map(([c, l]) => sw(c, l))}
      </Group>
      <Group gap="md">
        {sw("#3ec46d", "substation (worst unit's health)", true)}{sw("#ff3b6b", "open outage", true)}
        {storm && <><Text size="xs" c="dimmed">Storm paths:</Text>{EF_COLOR.map((c, i) => sw(c, `EF${i}`))}</>}
      </Group>
      {circuit && <Group gap="md"><Text size="xs" fw={600}>Equipment (by condition):</Text>
        {(["Good", "Fair", "Poor", "Critical", "Unknown"] as const).map(c => sw(CONDITION_HEX[c], c, true))}<Text size="xs" c="dimmed">black ring = damage confirmed · dashed line = sandbox route</Text></Group>}
      <Text size="xs" c="dimmed">Region areas are approximate (outline of each region's circuits). Network and storm data are a simulation.</Text>
    </Stack>
  );
}

function Kpis({ s }: { s: AssetSummary }) {
  return (
    <SimpleGrid cols={2} spacing="xs">
      <Stat label="Units on record" value={fmt(s.all.units)} hint={`${fmt(s.distribution.units)} distribution transformers`} />
      <Stat label="Poor / critical" value={fmt(s.all.poor)} color="orange" hint={pct(s.all.pct_poor)} />
      <Stat label="Not scored (unknown age)" value={fmt(s.all.unknown)} hint="install year not recorded" />
      <Stat label="Damage confirmed" value={fmt(s.all.damaged)} color={s.all.damaged ? "red" : undefined} hint="field assessments" />
    </SimpleGrid>
  );
}

function StatePanel({ summary, impact, event, onRegion }: { summary?: AssetSummary; impact?: StormImpact; event: StormEvent | null; onRegion: (id: string) => void }) {
  if (!summary) return <Loading />;
  const hit = new Map((impact?.regions_affected ?? []).map(r => [r.id, r]));
  return (
    <Stack gap="md">
      <Kpis s={summary} />
      {event && impact && (
        <Card withBorder>
          <Group justify="space-between" mb={6}><Text fw={600}>{event.name}</Text><Badge size="xs" variant="light" color="gray">prediction{impact.confirmed_damage.length ? " + field reports" : ""}</Badge></Group>
          <SimpleGrid cols={2} spacing={6}>
            <Text size="sm">{impact.circuits_hit.length} circuits {impact.kind === "tornado" ? "in the damage paths" : "heavily affected"}</Text>
            <Text size="sm">{impact.substations_exposed.length} substations feeding them</Text>
            <Text size="sm">{fmt(impact.assets_on_hit_circuits.reduce((s, a) => s + a.units, 0))} units to inspect</Text>
            <Text size="sm">{impact.critical_facilities.length} critical facilities</Text>
          </SimpleGrid>
          <Text size="xs" c="dimmed" mt={6}>Confirmed damage so far: {impact.confirmed_damage.length ? impact.confirmed_damage.map(d => `${d.units} ${d.label.toLowerCase()}s`).join(", ") : "none reported"}.</Text>
        </Card>)}
      <Card padding={0}>
        <Text fw={600} p="sm" pb={0}>Regions</Text>
        <Table highlightOnHover fz="sm">
          <Table.Thead><Table.Tr><Table.Th>Region</Table.Th><Table.Th ta="right">Circuits</Table.Th><Table.Th ta="right">Health</Table.Th><Table.Th ta="right">Poor</Table.Th>
            {event && <Table.Th ta="right">In storm path</Table.Th>}</Table.Tr></Table.Thead>
          <Table.Tbody>{summary.regions.map(r => (
            <Table.Tr key={r.id} className="row-click" onClick={() => onRegion(r.id)}>
              <Table.Td fw={600}>{r.name}</Table.Td><Table.Td ta="right">{r.circuits}</Table.Td>
              <Table.Td ta="right" c={hiColor(r.mean_hi)} fw={600}>{Math.round(r.mean_hi)}</Table.Td><Table.Td ta="right">{pct(r.pct_poor)}</Table.Td>
              {event && <Table.Td ta="right">{hit.get(r.id)?.circuits_hit ?? 0}</Table.Td>}
            </Table.Tr>))}</Table.Tbody>
        </Table>
        <Text size="xs" c="dimmed" p="sm">Click a region on the map or in the table to drill in.</Text>
      </Card>
    </Stack>
  );
}

function RegionPanel({ summary, subs, circuits, predBy, onSub, onCircuit }: { summary?: AssetSummary; subs?: SubstationRollup[]; circuits?: CircuitHealth[];
  predBy: Map<string, PredCircuit>; onSub: (id: string) => void; onCircuit: (c: CircuitHealth) => void }) {
  if (!summary || !subs || !circuits) return <Loading />;
  const worst = [...circuits].sort((a, b) => b.risk_all - a.risk_all).slice(0, 8);
  return (
    <Stack gap="md">
      <Kpis s={summary} />
      <Card padding={0}>
        <Text fw={600} p="sm" pb={0}>Substations ({subs.length})</Text>
        <Table highlightOnHover fz="sm">
          <Table.Thead><Table.Tr><Table.Th>Substation</Table.Th><Table.Th ta="right">Circuits</Table.Th><Table.Th ta="right">Customers</Table.Th>
            <Table.Th ta="right">Worst unit</Table.Th><Table.Th ta="right">Breakers poor</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{subs.map(x => (
            <Table.Tr key={x.id} className="row-click" onClick={() => onSub(x.id)}>
              <Table.Td><Text size="sm" fw={600}>{x.name}</Text><Text size="xs" c="dimmed">{x.zone}</Text></Table.Td>
              <Table.Td ta="right">{x.circuits}</Table.Td><Table.Td ta="right">{fmt(x.customers)}</Table.Td>
              <Table.Td ta="right" c={hiColor(x.worst_hi)} fw={600}>{x.worst_hi != null ? Math.round(x.worst_hi) : "—"}</Table.Td>
              <Table.Td ta="right">{x.breakers_poor}/{x.breakers}</Table.Td>
            </Table.Tr>))}</Table.Tbody>
        </Table>
      </Card>
      <CircuitList title="Highest-risk circuits" rows={worst} predBy={predBy} onCircuit={onCircuit} />
    </Stack>
  );
}

function CircuitList({ title, rows, predBy, onCircuit }: { title: string; rows: CircuitHealth[]; predBy: Map<string, PredCircuit>; onCircuit: (c: CircuitHealth) => void }) {
  return (
    <Card padding={0}>
      <Text fw={600} p="sm" pb={0}>{title}</Text>
      <Table highlightOnHover fz="sm">
        <Table.Thead><Table.Tr><Table.Th>Circuit</Table.Th><Table.Th ta="right">Health</Table.Th><Table.Th ta="right">Poor</Table.Th><Table.Th ta="right">Storm</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{rows.map(c => {
          const p = predBy.get(c.id);
          return (
            <Table.Tr key={c.id} className="row-click" onClick={() => onCircuit(c)}>
              <Table.Td><Text size="sm" ff="monospace" fw={600}>{c.id}</Text><Text size="xs" c="dimmed">{c.substation} · {fmt(c.customers)} cust.</Text></Table.Td>
              <Table.Td ta="right" c={hiColor(c.mean_hi)} fw={600}>{Math.round(c.mean_hi)}</Table.Td>
              <Table.Td ta="right">{pct(c.pct_poor)}</Table.Td>
              <Table.Td ta="right">{p ? (p.in_path ? <Badge size="xs" color="red">in path</Badge> : <Text size="xs">{pct(p.pct)}</Text>) : "—"}</Table.Td>
            </Table.Tr>);
        })}</Table.Tbody>
      </Table>
    </Card>
  );
}

function SubstationPanel({ d, failed, predBy, onCircuit, onAsset }: { d?: SubstationDetail; failed?: boolean; predBy: Map<string, PredCircuit>; onCircuit: (id: string) => void;
  onAsset: (id: string) => void }) {
  if (failed) return null;
  if (!d) return <Loading />;
  return (
    <Stack gap="md">
      <SimpleGrid cols={2} spacing="xs">
        <Stat label="Circuits" value={d.circuits} hint={`${fmt(d.customers)} customers`} />
        <Stat label="Worst substation unit" value={d.worst_hi != null ? Math.round(d.worst_hi) : "—"} color={d.worst_hi != null && d.worst_hi < 50 ? "red" : undefined} hint="health index" />
      </SimpleGrid>
      <Card padding={0}>
        <Text fw={600} p="sm" pb={0}>Substation equipment</Text>
        <Table highlightOnHover fz="sm"><Table.Tbody>{d.units.map(a => (
          <Table.Tr key={a.id} className="row-click" onClick={() => onAsset(a.id)}>
            <Table.Td><Text size="sm" fw={600}>{a.name}</Text><Text size="xs" c="dimmed" ff="monospace">{a.id}</Text></Table.Td>
            <Table.Td><AgeText a={a} /></Table.Td><Table.Td><HealthBadge hi={a.health_index} condition={a.condition} /></Table.Td>
          </Table.Tr>))}</Table.Tbody></Table>
      </Card>
      <CircuitList title="Circuits from this substation" rows={d.circuits_detail} predBy={predBy} onCircuit={c => onCircuit(c.id)} />
    </Stack>
  );
}

function CircuitPanel({ id, pred, outages, event, onAsset }: { id: string; pred?: PredCircuit; outages: Outage[]; event?: StormEvent | null; onAsset: (id: string) => void }) {
  const [kind, setKind] = useState<AssetKind>("dist_transformer");
  const [page, setPage] = useState(1);
  const { data: c, error } = useGet<CircuitHealthDetail>(`/assets/circuits/${id}?kind=${kind}&limit=${PAGE}&offset=${(page - 1) * PAGE}`);
  if (error) return null;  // the page shows "Circuit not found"
  if (!c) return <Loading />;
  if (c.id !== id) return <Loading />;
  return (
    <Stack gap="md">
      <Card withBorder>
        <Text fw={700} ff="monospace">{c.id}</Text>
        <Text size="sm" c="dimmed">{c.substation} · {c.zone} · {c.region} region · {fmt(c.customers)} customers · {c.overhead_pct}% overhead</Text>
        {c.critical_facility && <Text size="sm" c="red.4">Critical facility: {c.critical_facility}</Text>}
        {c.route_source === "synthetic" && <Text size="xs" c="dimmed" mt={4}>Route and topology are sandbox drawings, not the utility's GIS; equipment positions follow it.</Text>}
      </Card>
      {event && (
        <Card withBorder>
          <Text fw={600} mb={4}>{event.name} <Badge size="xs" variant="light" color="gray" ml={4}>prediction</Badge></Text>
          {pred ? <Text size="sm">{pred.in_path ? <b>In the predicted EF{pred.path_ef} damage path — plan a rebuild. </b> : pred.path_km != null ? `${pred.path_km} km from the nearest damage path. ` : ""}
            {fmt(pred.pred)} of {fmt(pred.customers)} customers predicted out ({pct(pred.pct)}), back in ~{Math.round(pred.eta_h)} h ({Math.round(pred.low_h)}–{Math.round(pred.high_h)} h).</Text>
            : <Text size="sm" c="dimmed">No prediction for this circuit.</Text>}
          <Text size="sm" mt={4}>Open outages now: <b>{outages.length}</b>{outages.length ? ` · ${fmt(outages.reduce((s, o) => s + o.customers, 0))} customers` : ""}
            {outages.some(o => o.asset_id) && <> · damaged units: {outages.filter(o => o.asset_id).map(o => <Anchor key={o.id} component="button" fz="sm" mx={2} onClick={() => onAsset(o.asset_id!)}>{o.asset_id}</Anchor>)}</>}</Text>
        </Card>)}
      <Card padding={0}>
        <Text fw={600} p="sm" pb={0}>Equipment on this circuit</Text>
        <Table highlightOnHover fz="sm">
          <Table.Thead><Table.Tr><Table.Th>Type</Table.Th><Table.Th ta="right">Units</Table.Th><Table.Th ta="right">Mean age</Table.Th><Table.Th ta="right">Health</Table.Th>
            <Table.Th ta="right">Poor</Table.Th><Table.Th ta="right">Unknown</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{c.kinds.filter(k => k.kind !== "power_transformer").map(k => (
            <Table.Tr key={k.kind} className="row-click" onClick={() => { setKind(k.kind); setPage(1); }} bg={k.kind === kind ? "var(--mantine-color-default-hover)" : undefined}>
              <Table.Td fw={k.kind === kind ? 700 : 400}>{KIND_PLURAL[k.kind]}</Table.Td><Table.Td ta="right">{fmt(k.units)}</Table.Td>
              <Table.Td ta="right">{k.mean_age} y</Table.Td><Table.Td ta="right" c={hiColor(k.mean_hi)} fw={600}>{Math.round(k.mean_hi)}</Table.Td>
              <Table.Td ta="right">{k.poor}</Table.Td><Table.Td ta="right">{k.unknown}</Table.Td>
            </Table.Tr>))}</Table.Tbody>
        </Table>
      </Card>
      <Card padding={0}>
        <Group justify="space-between" p="sm" pb={0}><Text fw={600}>{KIND_PLURAL[kind]} <Text span size="sm" c="dimmed">({fmt(c.list_total)}, highest risk first)</Text></Text></Group>
        {!c.transformers.length ? <Empty title="No units of this type on the circuit" /> : (
          <Table highlightOnHover fz="sm"><Table.Tbody>{c.transformers.map(a => (
            <Table.Tr key={a.id} className="row-click" onClick={() => onAsset(a.id)}>
              <Table.Td><Text size="sm" ff="monospace" fw={600}>{a.id}</Text><Text size="xs" c="dimmed">{a.name}</Text></Table.Td>
              <Table.Td><AgeText a={a} /></Table.Td>
              <Table.Td><HealthBadge hi={a.health_index} condition={a.condition} />{a.status === "damaged" && <Badge ml={4} size="xs" color="red">damaged</Badge>}</Table.Td>
              <Table.Td ta="right"><Tooltip label="Probability of failure in the next 12 months"><Text size="xs">{pct(a.pof_12m, 1)}</Text></Tooltip></Table.Td>
            </Table.Tr>))}</Table.Tbody></Table>)}
        {c.list_total > PAGE && <Group justify="center" p="xs"><Pagination size="sm" total={Math.ceil(c.list_total / PAGE)} value={page} onChange={setPage} /></Group>}
      </Card>
      <Text size="xs" c="dimmed">Replacement backlog on this circuit: {money(c.replacement_capex)} (Poor/Critical distribution transformers).</Text>
    </Stack>
  );
}
