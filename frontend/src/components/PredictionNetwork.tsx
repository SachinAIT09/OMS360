import { useState } from "react";
import { Alert, Badge, Button, Card, FileButton, Group, Modal, Progress, Select, Stack, Table, Text, Textarea, Tooltip } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconCloudDownload, IconFileUpload, IconInfoCircle } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet, useRoutes } from "../api/hooks";
import type { ForecastInfo, Prediction } from "../api/types";
import { dayjs, dt, dtShort, fmt, pct, sevColor } from "../lib/format";
import { Loading, SectionTitle } from "./common";
import { MapLegend, TerritoryMap } from "./TerritoryMap";

/** Hazard per zone from the parent company's storm model (or any imported forecast); drives the prediction. */
export function ForecastCard({ eventId, rain, canRun }: { eventId: number; rain: boolean; canRun: boolean }) {
  const { data } = useGet<ForecastInfo>(`/events/${eventId}/forecasts`);
  const [pasteOpen, paste] = useDisclosure(false);
  const [csv, setCsv] = useState("");
  const [source, setSource] = useState("Parent-company storm model");
  const imp = useAction((body: object) => api.post(`/events/${eventId}/forecasts`, body),
    { success: "Forecast imported — prediction re-run on it", invalidate: ["/events"] });
  if (!data) return <Card><Loading /></Card>;
  const fc = data.latest;
  const readFile = async (f: File | null) => { if (f) { setCsv(await f.text()); setSource(f.name.replace(/\.csv$/i, "")); paste.open(); } };

  return (
    <Card>
      <SectionTitle right={canRun && (
        <Group gap="xs">
          <Button size="xs" variant="default" leftSection={<IconCloudDownload size={14} />} loading={imp.isPending}
            onClick={() => imp.mutate({ mock: true, source: "Parent-company storm model" })}>Pull latest from parent model</Button>
          <FileButton onChange={readFile} accept=".csv,text/csv">
            {props => <Button size="xs" variant="default" leftSection={<IconFileUpload size={14} />} {...props}>Upload CSV</Button>}
          </FileButton>
          <Button size="xs" variant="subtle" onClick={() => { setCsv(data.sample_csv); paste.open(); }}>Paste rows</Button>
        </Group>
      )}>Forecast input</SectionTitle>
      {!fc ? (
        <Alert color="gray" icon={<IconInfoCircle size={18} />}>No outside forecast yet: the prediction uses one {rain ? "rainfall total" : "category"} for the whole territory.
          Import the parent company's storm model to give every zone (and from it every circuit) its own wind, rain, surge and arrival time.</Alert>
      ) : <>
        <Group gap="xs" mb="xs">
          <Badge variant="light" color="ai">{fc.source}</Badge>
          <Text size="xs" c="dimmed">issued {dt(fc.issued_at)} · imported by {fc.created_by} · {data.history.length} run{data.history.length === 1 ? "" : "s"} on file</Text>
        </Group>
        <Table.ScrollContainer minWidth={640}>
          <Table fz="sm" verticalSpacing={4}>
            <Table.Thead><Table.Tr><Table.Th>Zone</Table.Th><Table.Th ta="right">Peak gust</Table.Th><Table.Th ta="right">Rain</Table.Th><Table.Th ta="right">Surge</Table.Th><Table.Th>Arrival</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{[...fc.zones].sort((a, b) => (rain ? (b.rain_in ?? 0) - (a.rain_in ?? 0) : (b.gust_mph ?? 0) - (a.gust_mph ?? 0))).map(z => (
              <Table.Tr key={z.zone_id} c={z.filled ? "dimmed" : undefined}>
                <Table.Td>{z.zone}{z.filled && <Tooltip label="Not in the import; uses the advisory intensity"><Text span size="xs"> (filled)</Text></Tooltip>}</Table.Td>
                <Table.Td ta="right" className="tabular">{z.gust_mph != null ? `${Math.round(z.gust_mph)} mph` : "—"}</Table.Td>
                <Table.Td ta="right" className="tabular">{z.rain_in != null ? `${z.rain_in} in` : "—"}</Table.Td>
                <Table.Td ta="right" className="tabular">{z.surge_ft ? `${z.surge_ft} ft` : "—"}</Table.Td>
                <Table.Td>{z.arrival_at ? dtShort(z.arrival_at) : "—"}</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </>}
      <Text size="xs" c="dimmed" mt="xs">The parent model forecasts where and how hard the storm hits; OMS360 turns that into outages and restoration times per circuit using
        Bayview's network (overhead exposure, vegetation cycle, flood exposure) and crews. In this sandbox "Pull latest" generates the parent model's output.</Text>

      <Modal opened={pasteOpen} onClose={paste.close} title="Import forecast rows" size="lg">
        <Stack>
          <Select label="Source" data={["Parent-company storm model", "NHC advisory", "Internal meteorologist", source].filter((v, i, a) => a.indexOf(v) === i)}
            value={source} onChange={v => v && setSource(v)} allowDeselect={false} searchable />
          <Textarea label="CSV" description="Columns: zone (id, code or name), gust_mph, rain_in, surge_ft, arrival_at (ISO). Zones you leave out keep the advisory intensity."
            autosize minRows={8} ff="monospace" value={csv} onChange={ev => setCsv(ev.currentTarget.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={paste.close}>Cancel</Button>
            <Button loading={imp.isPending} onClick={async () => { await imp.mutateAsync({ csv, source }); paste.close(); }}>Import and re-run prediction</Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

const hrs = (h: number) => `${Math.round(h)} h`;

/** Predicted restoration by region and by circuit, with a likely range, before the first outage comes in. */
export function PredictedEtrTables({ p, impactAt, impactWord }: { p: Prediction; impactAt: string | null; impactWord: string }) {
  const [region, setRegion] = useState<string | null>(null);
  const [limit, setLimit] = useState(25);
  const routes = useRoutes();
  if (!p.circuits?.length) return null;
  const at = (h: number) => (impactAt ? dtShort(dayjs(impactAt).add(h, "hour").toISOString()) : null);
  const rows = p.circuits.filter(c => !region || c.region_id === region);
  const maxH = Math.max(...p.circuits.map(c => c.high_h));

  return (
    <>
      <Card padding={0}>
        <Text fw={600} p="md" pb={0}>Predicted restoration by region</Text>
        <Table.ScrollContainer minWidth={760}>
          <Table mt="xs">
            <Table.Thead><Table.Tr><Table.Th>Region</Table.Th><Table.Th ta="right">Predicted out</Table.Th><Table.Th ta="right">Circuits</Table.Th>
              <Table.Th>Typical customer back</Table.Th><Table.Th>Last circuit back</Table.Th><Table.Th ta="right">Confidence</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{p.regions!.map(r => (
              <Table.Tr key={r.id ?? r.name} className="row-click" onClick={() => setRegion(region === r.id ? null : r.id)}
                bg={region === r.id ? "var(--mantine-color-default-hover)" : undefined}>
                <Table.Td fw={600}>{r.name}</Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(r.pred)}</Table.Td>
                <Table.Td ta="right" className="tabular">{r.circuits}</Table.Td>
                <Table.Td><Text size="sm" fw={600}>{hrs(r.eta_h)} <Text span size="xs" c="dimmed">({hrs(r.low_h)}–{hrs(r.high_h)})</Text></Text>
                  {at(r.eta_h) && <Text size="xs" c="dimmed">~{at(r.eta_h)}</Text>}</Table.Td>
                <Table.Td><Text size="sm">{hrs(r.last_h)} <Text span size="xs" c="dimmed">(up to {hrs(r.last_high_h)})</Text></Text></Table.Td>
                <Table.Td ta="right">{r.confidence}%</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Text size="xs" c="dimmed" p="sm">Hours after {impactWord}. Typical = customer-weighted across the region's circuits; range = likely low–high. Click a region to filter the circuits below.</Text>
      </Card>

      <Card padding="sm">
        <Text fw={600} mb="xs">Predicted impact by circuit {region && <Badge ml={6} variant="light">{p.regions!.find(r => r.id === region)?.name}</Badge>}</Text>
        <TerritoryMap height={420} lines={(() => {
          const byId = new Map(rows.map(c => [c.id, c]));
          return (routes.data?.feeders ?? []).filter(f => byId.has(f.id) && f.route.length).sort((a, b) => byId.get(a.id)!.pct - byId.get(b.id)!.pct).map(f => {
            const c = byId.get(f.id)!;
            return { id: f.id, lines: f.route, color: sevColor(c.pct), weight: 2 + c.pct * 8,
              popup: <div><b>{c.id}</b> · {c.substation} · {c.zone}<br />Predicted {fmt(c.pred)} of {fmt(c.customers)} out ({pct(c.pct)})<br />
                Back in ~{hrs(c.eta_h)} ({hrs(c.low_h)}–{hrs(c.high_h)}) after {impactWord}{at(c.eta_h) ? ` · ${at(c.eta_h)}` : ""}</div> };
          });
        })()} />
        <MapLegend mode="pred" />
      </Card>

      <Card padding={0}>
        <Group p="md" pb={0} justify="space-between">
          <Text fw={600}>Predicted restoration by circuit {region && <Badge ml={6} variant="light">{p.regions!.find(r => r.id === region)?.name}</Badge>}</Text>
          <Select size="xs" w={170} placeholder="All regions" clearable value={region} onChange={setRegion}
            data={p.regions!.filter(r => r.id).map(r => ({ value: r.id!, label: r.name }))} />
        </Group>
        <Table.ScrollContainer minWidth={900}>
          <Table mt="xs">
            <Table.Thead><Table.Tr><Table.Th>Circuit</Table.Th><Table.Th>Substation · zone</Table.Th><Table.Th ta="right">Predicted out</Table.Th>
              <Table.Th w={260}>Restoration (likely range)</Table.Th><Table.Th ta="right">Confidence</Table.Th><Table.Th ta="right">Overhead</Table.Th><Table.Th ta="right">Last trim</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.slice(0, limit).map(c => (
              <Table.Tr key={c.id}>
                <Table.Td ff="monospace" fz="sm" fw={600}>{c.id}</Table.Td>
                <Table.Td><Text size="sm">{c.substation ?? "—"}</Text><Text size="xs" c="dimmed">{c.zone} · {c.region}</Text></Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(c.pred)} <Text span size="xs" c="dimmed">of {fmt(c.customers)}</Text></Table.Td>
                <Table.Td>
                  <Tooltip label={`${hrs(c.low_h)} – ${hrs(c.high_h)} after ${impactWord}${at(c.eta_h) ? ` · most likely ${at(c.eta_h)}` : ""}`}>
                    <div>
                      <Text size="sm" fw={600}>{hrs(c.eta_h)} <Text span size="xs" c="dimmed">({hrs(c.low_h)}–{hrs(c.high_h)})</Text></Text>
                      <Progress.Root size="sm" mt={2}>
                        <Progress.Section value={(c.low_h / maxH) * 100} color="transparent" />
                        <Progress.Section value={((c.high_h - c.low_h) / maxH) * 100} color="brand.4" />
                      </Progress.Root>
                    </div>
                  </Tooltip>
                </Table.Td>
                <Table.Td ta="right">{c.confidence}%</Table.Td>
                <Table.Td ta="right">{c.overhead_pct}%</Table.Td>
                <Table.Td ta="right">{c.years_since_trim} y ago</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group p="sm" justify="space-between">
          <Text size="xs" c="dimmed">Circuit hours = zone hours scaled by the circuit's overhead exposure and vegetation cycle. Ranges are wider without an outside forecast,
            when crews are short, and on mostly-overhead circuits.</Text>
          {rows.length > limit && <Button size="xs" variant="subtle" onClick={() => setLimit(l => l + 50)}>Show more ({rows.length - limit})</Button>}
        </Group>
      </Card>
    </>
  );
}
