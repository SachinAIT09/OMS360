import { useState } from "react";
import { Alert, Anchor, Badge, Button, Card, FileButton, Grid, Group, List, Stack, Text } from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconFileUpload, IconRefresh } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useRoutes } from "../api/hooks";
import { fmt } from "../lib/format";
import { Loading, SectionTitle } from "./common";
import { TerritoryMap } from "./TerritoryMap";

interface ImportResult { matched: number; unmatched: number; unmatched_ids: string[]; missing_id: number }

const TEMPLATE = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", properties: { feeder_id: "FDR-TPA-01", substation: "Tampa North", customers: 6200 },
      geometry: { type: "LineString", coordinates: [[-82.47, 27.962], [-82.47, 27.97], [-82.462, 27.97], [-82.462, 27.978]] } },
    { type: "Feature", properties: { feeder_id: "FDR-TPA-02", substation: "Tampa North", customers: 5400 },
      geometry: { type: "MultiLineString", coordinates: [[[-82.47, 27.962], [-82.478, 27.962], [-82.478, 27.955]], [[-82.478, 27.962], [-82.486, 27.962]]] } },
  ],
};

/** Circuit routes: where they come from and how to load the utility's GIS export. */
export function NetworkAdmin() {
  const routes = useRoutes();
  const [result, setResult] = useState<ImportResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const imp = useAction((body: object) => api.post<ImportResult>("/admin/network/feeders", body),
    { success: r => `${r.matched} circuit routes imported`, invalidate: ["/network", "/admin"] });
  const reset = useAction(() => api.post<{ reset: number }>("/admin/network/feeders/reset", {}),
    { success: "Routes reset to sandbox drawings", invalidate: ["/network", "/admin"] });
  if (!routes.data) return <Loading />;
  const c = routes.data.counts;
  const total = routes.data.feeders.length;

  const upload = async (f: File | null) => {
    if (!f) return;
    setErr(null); setResult(null);
    let json: object;
    try { json = JSON.parse(await f.text()); } catch { setErr(`${f.name} isn't valid JSON. Export the feeder layer as GeoJSON.`); return; }
    try { setResult(await imp.mutateAsync(json)); } catch (e) { setErr((e as Error).message); }
  };
  const template = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(TEMPLATE, null, 2)], { type: "application/geo+json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "feeder-routes-template.geojson" });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Grid gutter="lg">
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <Stack>
          <Card>
            <SectionTitle right={<Badge color={c.imported ? "teal" : "yellow"} variant="light">{c.imported ? "GIS data loaded" : "Sandbox routes"}</Badge>}>Circuit routes</SectionTitle>
            <Group gap="xl" mb="sm">
              <div><Text size="xs" c="dimmed">Circuits</Text><Text fw={700} size="lg">{fmt(total)}</Text></div>
              <div><Text size="xs" c="dimmed">From utility GIS</Text><Text fw={700} size="lg" c="teal">{fmt(c.imported ?? 0)}</Text></div>
              <div><Text size="xs" c="dimmed">Sandbox drawn</Text><Text fw={700} size="lg">{fmt(c.synthetic ?? 0)}</Text></div>
              <div><Text size="xs" c="dimmed">Substations</Text><Text fw={700} size="lg">{routes.data.substations.length}</Text></div>
            </Group>
            <Text size="sm" c="dimmed" mb="md">Routes draw circuits on the restoration board, the impact prediction and the public outage map.
              Until the utility's feeder layer is imported, OMS360 draws each circuit from its substation along a street-grid path.</Text>
            <Group gap="xs">
              <FileButton onChange={upload} accept=".geojson,.json,application/geo+json,application/json">
                {props => <Button leftSection={<IconFileUpload size={16} />} loading={imp.isPending} {...props}>Import feeder GeoJSON</Button>}
              </FileButton>
              <Button variant="default" onClick={template}>Download template</Button>
              {!!c.imported && <Button variant="subtle" color="gray" leftSection={<IconRefresh size={16} />} loading={reset.isPending}
                onClick={() => modals.openConfirmModal({ title: "Reset circuit routes", children: <Text size="sm">Replace the {c.imported} imported routes with sandbox drawings?</Text>,
                  labels: { confirm: "Reset", cancel: "Cancel" }, onConfirm: () => reset.mutate() })}>Reset to sandbox</Button>}
            </Group>
            {err && <Alert mt="md" color="red" p="xs">{err}</Alert>}
            {result && <Alert mt="md" color={result.unmatched ? "yellow" : "teal"} p="xs">
              {result.matched} circuits matched and drawn from the file.
              {result.unmatched > 0 && <> {result.unmatched} feeder IDs aren't in OMS360 yet{result.unmatched_ids.length ? `: ${result.unmatched_ids.slice(0, 8).join(", ")}${result.unmatched > 8 ? "…" : ""}` : ""}.</>}
              {result.missing_id > 0 && <> {result.missing_id} features had no feeder ID property.</>}
            </Alert>}
          </Card>
          <Card>
            <SectionTitle>What the file needs</SectionTitle>
            <List size="sm" spacing={4}>
              <List.Item><b>GeoJSON FeatureCollection</b> of the feeder primary lines (LineString or MultiLineString). A circuit may span several features.</List.Item>
              <List.Item><b>WGS84 coordinates</b> (EPSG:4326). From a State Plane layer, in QGIS use Export → Save Features As → GeoJSON, CRS EPSG:4326.</List.Item>
              <List.Item>A <b>feeder ID</b> property per feature (<code>feeder_id</code>, <code>circuit</code>, <code>feeder</code> or <code>id</code>) holding the same ID the outage system puts on tickets.</List.Item>
              <List.Item>Optional: <code>customers</code> (updates the circuit's customer count) and <code>substation</code>.</List.Item>
            </List>
            <Text size="xs" c="dimmed" mt="sm">Shapefile or file geodatabase? Convert with QGIS or <Anchor href="https://mapshaper.org" target="_blank" size="xs">mapshaper.org</Anchor> (export GeoJSON, WGS84).</Text>
          </Card>
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <Card padding="sm">
          <TerritoryMap height={560}
            lines={routes.data.feeders.filter(f => f.route.length).map(f => ({ id: f.id, lines: f.route, color: f.source === "imported" ? "#3ec46d" : "#4d8dff", weight: 2,
              popup: <div><b>{f.id}</b><br />{f.substation} · {f.zone}<br />{f.source === "imported" ? "From utility GIS" : "Sandbox drawing"}</div> }))}
            pins={routes.data.substations.map(x => ({ id: x.id, lat: x.lat, lng: x.lng, color: "#f5a623", popup: <div><b>{x.name}</b> substation</div> }))} />
          <Group gap="md" mt={6}>
            {[["#3ec46d", "from utility GIS"], ["#4d8dff", "sandbox drawing"], ["#f5a623", "substation"]].map(([col, l]) => (
              <Group key={l} gap={4}><div style={{ width: 14, height: 3, background: col }} /><Text size="xs" c="dimmed">{l}</Text></Group>))}
          </Group>
        </Card>
      </Grid.Col>
    </Grid>
  );
}
