import { useState } from "react";
import { Badge, Card, ColorSwatch, Grid, Group, Select, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import { AreaChart, BarChart, DonutChart } from "@mantine/charts";
import { useGet } from "../api/hooks";
import type { Curve, StormEvent } from "../api/types";
import { EventStatusBadge } from "../components/badges";
import { Loading, PageHeader, SectionTitle, Stat } from "../components/common";
import { date, dtShort, fmt, label } from "../lib/format";

interface Summary {
  event: StormEvent; tickets: number; customers_affected: number; predicted: number | null; prediction_error_pct: number | null; restored_tickets: number;
  avg_restore_h: number | null; median_restore_h: number | null; customer_minutes: number; saidi_min: number; etr_mae_h: number | null;
  etr_within_2h_pct: number | null; mutual_aid_workers: number; messages_sent: number; message_recipients: number; crews_used: number;
}
interface Detail {
  summary: Summary; zones: { zone: string; tickets: number; customers: number; avg_restore_h: number | null }[]; causes: { cause: string; tickets: number }[];
  channels: { channel: string; messages: number; recipients: number }[]; crews: { code: string; company: string; tickets: number }[]; curve: Curve;
}
const COLORS = ["red.6", "orange.6", "yellow.6", "blue.6", "cyan.6", "gray.6"];
const CHANNEL_LABELS: Record<string, string> = { sms: "SMS", x: "X", ivr: "IVR" };
const channelLabel = (c: string) => CHANNEL_LABELS[c.toLowerCase()] ?? label(c);

export default function ReportsPage() {
  const { data: rows } = useGet<Summary[]>("/reports/events");
  const [sel, setSel] = useState<string | null>(null);
  const id = sel ?? (rows?.find(r => r.tickets > 0) ?? rows?.[0])?.event.id.toString() ?? null;
  const { data: d } = useGet<Detail>(id ? `/reports/events/${id}` : null);
  if (!rows) return <Loading />;
  const causes = (d?.causes ?? []).map((c, i) => ({ name: label(c.cause), value: c.tickets, color: COLORS[i % COLORS.length] }));
  const causeTotal = causes.reduce((s, c) => s + c.value, 0);
  return (
    <>
      <PageHeader title="Reports" description="Storm performance: restoration, ETR accuracy, workforce and customer communications." />
      <Card padding={0} mb="lg">
        <Table.ScrollContainer minWidth={1000}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Event</Table.Th><Table.Th>Status</Table.Th><Table.Th ta="right">Customers affected</Table.Th><Table.Th ta="right">Predicted</Table.Th>
              <Table.Th ta="right">Tickets</Table.Th><Table.Th ta="right">Avg restore</Table.Th><Table.Th ta="right">SAIDI (min)</Table.Th><Table.Th ta="right">ETR error</Table.Th><Table.Th ta="right">Mutual aid</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{rows.map(r => (
              <Table.Tr key={r.event.id} className="row-click" onClick={() => setSel(String(r.event.id))} bg={String(r.event.id) === id ? "var(--mantine-color-default-hover)" : undefined}>
                <Table.Td><Text size="sm" fw={600}>{r.event.name}</Text><Text size="xs" c="dimmed">{date(r.event.landfall_at ?? r.event.created_at)}</Text></Table.Td>
                <Table.Td><EventStatusBadge status={r.event.status} size="sm" /></Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(r.customers_affected)}</Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(r.predicted)}{r.prediction_error_pct != null && <Text span size="xs" c="dimmed"> ({r.prediction_error_pct > 0 ? "+" : ""}{r.prediction_error_pct}%)</Text>}</Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(r.tickets)}</Table.Td>
                <Table.Td ta="right">{r.avg_restore_h != null ? `${r.avg_restore_h} h` : "—"}</Table.Td>
                <Table.Td ta="right">{r.saidi_min || "—"}</Table.Td>
                <Table.Td ta="right">{r.etr_mae_h != null ? `±${r.etr_mae_h} h` : "—"}</Table.Td>
                <Table.Td ta="right">{fmt(r.mutual_aid_workers)}</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      {d && <>
        <Group justify="space-between" mb="sm"><Text fw={700} size="lg">{d.summary.event.name}</Text>
          <Select size="sm" w={260} value={id} onChange={setSel} data={rows.map(r => ({ value: String(r.event.id), label: r.event.name }))} /></Group>
        <SimpleGrid cols={{ base: 2, md: 3, xl: 6 }} mb="lg">
          <Stat label="Customers affected" value={fmt(d.summary.customers_affected)} />
          <Stat label="Median restoration" value={d.summary.median_restore_h != null ? `${d.summary.median_restore_h} h` : "—"} />
          <Stat label="Customer minutes" value={fmt(d.summary.customer_minutes)} hint={`SAIDI ${d.summary.saidi_min} min`} />
          <Stat label="ETR accuracy" value={d.summary.etr_within_2h_pct != null ? `${d.summary.etr_within_2h_pct}%` : "—"} color="teal" hint={d.summary.etr_mae_h != null ? `within 2 h · mean error ±${d.summary.etr_mae_h} h` : undefined} />
          <Stat label="Crews used" value={fmt(d.summary.crews_used)} hint={`${fmt(d.summary.mutual_aid_workers)} mutual-aid workers`} />
          <Stat label="Messages sent" value={fmt(d.summary.messages_sent)} hint={`${fmt(d.summary.message_recipients)} recipients`} />
        </SimpleGrid>
        <Grid gutter="lg">
          <Grid.Col span={{ base: 12, lg: 8 }}>
            <Card h="100%"><SectionTitle>Customers out over time</SectionTitle>
              {d.curve.points.length ? <AreaChart h={260} data={d.curve.points.map(p => ({ t: dtShort(p.at), "Customers out": p.out }))} dataKey="t" series={[{ name: "Customers out", color: "red.6" }]}
                curveType="monotone" withDots={false} gridAxis="y" valueFormatter={v => fmt(v)} /> : <Text c="dimmed">No outages recorded.</Text>}
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 4 }}>
            <Card h="100%"><SectionTitle>Causes</SectionTitle>
              {d.causes.length ? <>
                <Group justify="center"><DonutChart size={170} thickness={24} withTooltip data={causes} /></Group>
                <Stack gap={6} mt="md">{causes.map(c => (
                  <Group key={c.name} justify="space-between" wrap="nowrap">
                    <Group gap="xs" wrap="nowrap"><ColorSwatch color={`var(--mantine-color-${c.color.replace(".", "-")})`} size={10} withShadow={false} /><Text size="sm">{c.name}</Text></Group>
                    <Text size="sm" className="tabular">{c.value} <Text span size="xs" c="dimmed">({causeTotal ? Math.round(c.value / causeTotal * 100) : 0}%)</Text></Text>
                  </Group>))}
                </Stack>
              </> : <Text c="dimmed">No causes recorded.</Text>}
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card h="100%"><SectionTitle>Impact by zone</SectionTitle>
              <BarChart h={Math.max(280, d.zones.length * 44)} orientation="vertical" data={d.zones.map(z => ({ zone: z.zone, Customers: z.customers }))} dataKey="zone"
                series={[{ name: "Customers", color: "brand.6" }]} gridAxis="x" valueFormatter={v => fmt(v)} yAxisProps={{ width: 110, interval: 0 }} />
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card padding={0} h="100%">
              <Text fw={600} p="md" pb={0}>Restoration time by zone</Text>
              <Table mt="xs"><Table.Thead><Table.Tr><Table.Th>Zone</Table.Th><Table.Th ta="right">Tickets</Table.Th><Table.Th ta="right">Customers</Table.Th><Table.Th ta="right">Avg restore</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>{d.zones.map(z => <Table.Tr key={z.zone}><Table.Td>{z.zone}</Table.Td><Table.Td ta="right">{z.tickets}</Table.Td><Table.Td ta="right" className="tabular">{fmt(z.customers)}</Table.Td>
                  <Table.Td ta="right">{z.avg_restore_h != null ? `${z.avg_restore_h} h` : "—"}</Table.Td></Table.Tr>)}</Table.Tbody></Table>
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card padding={0} h="100%">
              <Text fw={600} p="md" pb={0}>Communications by channel</Text>
              <Table mt="xs"><Table.Tbody>{d.channels.map(c => <Table.Tr key={c.channel}><Table.Td>{channelLabel(c.channel)}</Table.Td><Table.Td ta="right">{c.messages} {c.messages === 1 ? "message" : "messages"}</Table.Td>
                <Table.Td ta="right" className="tabular">{fmt(c.recipients)} recipients</Table.Td></Table.Tr>)}</Table.Tbody></Table>
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}>
            <Card padding={0} h="100%">
              <Text fw={600} p="md" pb={0}>Most productive crews</Text>
              <Table mt="xs"><Table.Tbody>{d.crews.slice(0, 6).map(c => <Table.Tr key={c.code}><Table.Td><Badge variant="outline">{c.code}</Badge></Table.Td><Table.Td>{c.company}</Table.Td>
                <Table.Td ta="right">{c.tickets} tickets</Table.Td></Table.Tr>)}</Table.Tbody></Table>
            </Card>
          </Grid.Col>
        </Grid>
      </>}
    </>
  );
}
