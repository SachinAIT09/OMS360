import { useState } from "react";
import { Alert, Anchor, Autocomplete, Badge, Box, Button, Card, Container, Grid, Group, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { IconAlertTriangle, IconBolt, IconCircleCheck, IconClock, IconSearch } from "@tabler/icons-react";
import { api, ApiError } from "../api/client";
import { TerritoryMap } from "../components/TerritoryMap";
import { dt, fmt, pct } from "../lib/format";

interface PublicMap {
  event: { name: string; status: string; landfall_at: string | null } | null; customers_out: number; restored_pct: number | null; sample_addresses: string[];
  zones: { id: string; short: string; lat: number; lng: number; customers: number; customers_out: number; pct_out: number; etr_at: string | null }[];
  circuits?: { id: string; zone: string; substation: string | null; lat: number; lng: number; customers_out: number; etr_at: string | null; confidence: number; route: [number, number][][] }[];
}
interface Lookup {
  status: "no_outage" | "restored" | "etr" | "confirmed"; zone: string; address: string; circuit?: string; event: string | null;
  level?: "circuit" | "zone"; etr_at?: string; crews?: number; confidence?: number;
}

/** Customer-facing outage center (no sign-in). Always light, as on the utility website (forced in main.tsx). */
export default function PublicOutageMap() {
  const { data } = useQuery({ queryKey: ["/public/outage-map"], queryFn: () => api.get<PublicMap>("/public/outage-map"), refetchInterval: 30_000 });
  const [addr, setAddr] = useState("");
  const [result, setResult] = useState<Lookup | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const lookup = async (a = addr) => {
    setErr(null);
    try { setResult(await api.get<Lookup>(`/public/lookup?address=${encodeURIComponent(a)}`)); } catch (e) { setResult(null); setErr(e instanceof ApiError ? e.message : "Lookup failed"); }
  };
  const ev = data?.event;
  const banner = !ev ? null : ev.status === "monitoring" || ev.status === "preparing"
    ? { c: "yellow", t: `${ev.name} may affect our service area${ev.landfall_at ? ` around ${dt(ev.landfall_at)}` : ""}. Prepare now and sign up for outage alerts.` }
    : ev.status === "active" ? { c: "red", t: `${ev.name}: ${fmt(data!.customers_out)} customers are without power. Crews work as soon as conditions are safe.` }
    : { c: "blue", t: `Restoration in progress — ${pct(data!.restored_pct)} of affected customers restored.` };

  return (
    <Box bg="gray.0" mih="100vh">
      <Box bg="#0b3d91" c="white" py="md">
        <Container size="lg"><Group justify="space-between">
          <Group gap="sm"><Box w={32} h={32} style={{ borderRadius: 8, background: "linear-gradient(135deg,#6f9dff,#3ec46d)" }} />
            <div><Text fw={700} size="lg" lh={1.1}>Bayview Power & Water</Text><Text size="xs" opacity={0.8}>Outage Center</Text></div></Group>
          <Group gap="lg" visibleFrom="sm"><Text size="sm">Outage map</Text><Text size="sm">Report an outage</Text><Text size="sm">Storm center</Text><Text size="sm">Alerts</Text></Group>
        </Group></Container>
      </Box>
      {banner && <Alert color={banner.c} variant="filled" radius={0} icon={<IconAlertTriangle size={18} />}><Container size="lg" p={0}>{banner.t}</Container></Alert>}
      <Container size="lg" py="xl">
        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, md: 5 }}>
            <Stack>
              <Card withBorder radius="md" padding="lg">
                <Title order={4} mb="sm">Check your address</Title>
                <Group gap="xs" align="flex-end">
                  <Autocomplete style={{ flex: 1 }} placeholder="Street address" data={data?.sample_addresses ?? []} value={addr} onChange={setAddr} onOptionSubmit={v => lookup(v)}
                    onKeyDown={e => e.key === "Enter" && lookup()} leftSection={<IconSearch size={16} />} />
                  <Button color="#0b3d91" onClick={() => lookup()}>Check</Button>
                </Group>
                {err && <Text c="red" size="sm" mt="sm">{err}</Text>}
              </Card>
              {result && (
                <Paper withBorder radius="md" p="lg" style={{ borderColor: "#b8c8f0" }}>
                  <Text size="xs" c="dimmed">{result.address}</Text>
                  {result.status === "no_outage" && <Group mt={6} gap="xs"><IconCircleCheck color="green" /><Text fw={600}>No outage reported at this address</Text></Group>}
                  {result.status === "restored" && <Group mt={6} gap="xs"><IconCircleCheck color="green" /><Text fw={600} c="green.8">Power restored in {result.zone}</Text></Group>}
                  {result.status === "confirmed" && <><Group mt={6} gap="xs"><IconBolt color="#c92a2a" /><Text fw={600} c="red.8">Outage confirmed</Text></Group>
                    <Text size="sm" c="dimmed" mt={4}>We know your power is out. Your estimated restoration time will appear here once crews have assessed the damage.</Text></>}
                  {result.status === "etr" && result.etr_at && <>
                    <Text size="xs" tt="uppercase" fw={600} c="dimmed" mt="xs">Estimated restoration</Text>
                    <Title order={2} c="#0b3d91">{dt(result.etr_at)}</Title>
                    <Text size="sm" c="dimmed" mt={4}>{result.level === "circuit"
                      ? `Estimate for your circuit ${result.circuit} in ${result.zone}: ${result.crews} crews are on it. This estimate updates automatically.`
                      : `${result.crews} crews are working in ${result.zone}. This estimate updates automatically.`}</Text>
                    <Badge mt="sm" variant="light" leftSection={<IconClock size={12} />}>{result.confidence}% confidence</Badge>
                  </>}
                </Paper>
              )}
              <SimpleGrid cols={2}>
                <Card withBorder radius="md"><Text size="xs" c="dimmed">Customers without power</Text><Text fw={700} size="xl" c="red.8">{fmt(data?.customers_out ?? 0)}</Text></Card>
                <Card withBorder radius="md"><Text size="xs" c="dimmed">Restored</Text><Text fw={700} size="xl" c="green.8">{data?.restored_pct != null ? pct(data.restored_pct) : "—"}</Text></Card>
              </SimpleGrid>
              <Card withBorder radius="md"><Text fw={600}>Get outage alerts</Text><Text size="sm" c="dimmed">Text <b>REG</b> to 72990 to receive outage and restoration updates.</Text></Card>
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Card withBorder radius="md" padding="xs">
              <TerritoryMap light height={480} zones={(data?.zones ?? []).map(z => ({ id: z.id, short: z.short, lat: z.lat, lng: z.lng, customers: z.customers, value: z.pct_out,
                popup: <div><b>{z.short}</b><br />{fmt(z.customers_out)} customers out<br />{z.etr_at ? `Estimated restoration ${dt(z.etr_at)}` : z.customers_out ? "Assessing damage" : "No outages"}</div> }))}
                lines={(data?.circuits ?? []).filter(c => c.route.length).map(c => ({ id: c.id, lines: c.route, color: "#2b6bff", weight: 4,
                  popup: <div><b>Circuit {c.id}</b> · {c.zone}<br />Estimated restoration {dt(c.etr_at)}<br />{c.confidence}% confidence</div> }))}
                pins={Object.values((data?.circuits ?? []).reduce<Record<string, NonNullable<PublicMap["circuits"]>>>((acc, c) => {
                  (acc[c.substation ?? c.id] ??= []).push(c); return acc;
                }, {})).map(cs => ({ id: cs[0].substation ?? cs[0].id, lat: cs[0].lat, lng: cs[0].lng, color: "#2b6bff",
                  popup: <div><b>{cs[0].substation ?? cs[0].zone} area</b>{cs.map(c => <div key={c.id}>Circuit {c.id}: back by {dt(c.etr_at)} ({c.confidence}% confidence)</div>)}</div> }))} />
            </Card>
            <Text size="xs" c="dimmed" mt="xs">Circles show the share of customers without power by community; blue lines are circuits with their own restoration time. Updated every 30 seconds. <Anchor href="/login" size="xs">Staff sign-in</Anchor></Text>
          </Grid.Col>
        </Grid>
      </Container>
    </Box>
  );
}
