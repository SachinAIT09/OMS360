/* Statewide impact of a storm on the network: what the prediction puts in the storm's path (regions, substations, circuits,
   equipment to inspect, critical facilities) next to what field crews have actually confirmed. */
import { Link, useNavigate } from "react-router-dom";
import { Anchor, Badge, Card, Group, SimpleGrid, Stack, Table, Text, Tooltip } from "@mantine/core";
import { useGet } from "../api/hooks";
import type { StormImpact } from "../api/types";
import { fmt, pct } from "../lib/format";
import { Loading } from "./common";

export function StormImpactCard({ eventId }: { eventId: number }) {
  const { data: d } = useGet<StormImpact>(`/events/${eventId}/impact`, { refetchInterval: 60_000 });
  const go = useNavigate();
  if (!d) return <Card><Loading /></Card>;
  if (!d.basis) return null;
  const tornado = d.kind === "tornado";
  const inspect = d.assets_on_hit_circuits.reduce((s, a) => s + a.units, 0);
  return (
    <Card>
      <Group justify="space-between" mb="sm" wrap="wrap">
        <Text fw={600}>Network impact {tornado ? "— circuits in the damage paths" : "— most affected circuits"}</Text>
        <Group gap={6}>
          <Tooltip label="From the latest impact prediction — not confirmed damage"><Badge variant="light" color="gray">Prediction</Badge></Tooltip>
          <Badge variant="light" color={d.confirmed_damage.length ? "red" : "gray"}>{d.confirmed_damage.length ? "Field reports in" : "No field reports yet"}</Badge>
          <Anchor component={Link} to="/network" fz="sm">Open network explorer</Anchor>
        </Group>
      </Group>
      <SimpleGrid cols={{ base: 2, md: 5 }} spacing="xs" mb="sm">
        <Fig label="Regions affected" value={d.regions_affected.filter(r => r.circuits_hit).length || d.regions_affected.length} />
        <Fig label={tornado ? "Circuits in path" : "Circuits ≥ 30% out"} value={d.circuits_hit.length} />
        <Fig label="Substations feeding them" value={d.substations_exposed.length} />
        <Fig label="Units to inspect" value={fmt(inspect)} hint={`${fmt(d.assets_on_hit_circuits.reduce((s, a) => s + a.poor_or_unknown, 0))} poor or unscored`} />
        <Fig label="Damage confirmed" value={fmt(d.confirmed_damage.reduce((s, a) => s + a.units, 0))} hint="field assessments" red={!!d.confirmed_damage.length} />
      </SimpleGrid>
      <Stack gap={6}>
        {d.circuits_hit.length > 0 && (
          <Table.ScrollContainer minWidth={560}>
            <Table fz="sm" highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>Circuit</Table.Th><Table.Th>Substation · region</Table.Th><Table.Th ta="right">Customers</Table.Th>
                <Table.Th ta="right">Predicted out</Table.Th><Table.Th ta="right">Back in</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{d.circuits_hit.slice(0, 8).map(c => (
                <Table.Tr key={c.id} className="row-click" onClick={() => go(`/network?circuit=${c.id}`)}>
                  <Table.Td ff="monospace" fw={600}>{c.id}{c.path_ef != null && tornado && <Badge ml={6} size="xs" color="red" variant="light">EF{c.path_ef}</Badge>}</Table.Td>
                  <Table.Td>{c.substation} · {c.region}</Table.Td><Table.Td ta="right">{fmt(c.customers)}</Table.Td>
                  <Table.Td ta="right">{pct(c.pct)}</Table.Td><Table.Td ta="right">~{Math.round(c.eta_h)} h</Table.Td>
                </Table.Tr>))}</Table.Tbody>
            </Table>
          </Table.ScrollContainer>)}
        {d.critical_facilities.length > 0 && <Text size="sm"><b>Critical facilities on these circuits:</b> {d.critical_facilities.map(f => `${f.name} (${f.feeder})`).join(", ")}</Text>}
        <Text size="xs" c="dimmed">{d.scenario} · simulation data. Units to inspect are every transformer, pole and switch on those circuits; damage is counted only when a
          crew confirms it on an outage ticket.</Text>
      </Stack>
    </Card>
  );
}

function Fig({ label, value, hint, red }: { label: string; value: string | number; hint?: string; red?: boolean }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: ".04em" }}>{label}</Text>
      <Text fz={22} fw={700} c={red ? "red.5" : undefined} className="tabular">{value}</Text>
      {hint && <Text size="xs" c="dimmed">{hint}</Text>}
    </div>
  );
}
