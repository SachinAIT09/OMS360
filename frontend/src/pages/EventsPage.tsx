import { useNavigate } from "react-router-dom";
import { Alert, Anchor, Badge, Button, Card, Grid, Group, Modal, NumberInput, Select, Stack, Table, Text, Textarea, TextInput } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { IconAlertTriangle, IconCloudDownload, IconPlus, IconSatellite } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet } from "../api/hooks";
import type { NhcStorm, StormEvent } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { EventStatusBadge } from "../components/badges";
import { Empty, Loading, PageHeader } from "../components/common";
import { ago, date, dt, fmt } from "../lib/format";

export default function EventsPage() {
  const { can } = useAuth();
  const go = useNavigate();
  const { setEventId } = useCurrentEvent();
  const { data } = useGet<StormEvent[]>("/events");
  const [newOpen, newCtl] = useDisclosure(false);
  const [nhcOpen, nhcCtl] = useDisclosure(false);

  return (
    <>
      <PageHeader title="Storm events" description="Every storm the utility prepares for, responds to and reports on."
        actions={can("events.manage") && <>
          <Button variant="default" leftSection={<IconSatellite size={16} />} onClick={nhcCtl.open}>Import from NHC</Button>
          <Button leftSection={<IconPlus size={16} />} onClick={newCtl.open}>New event</Button>
        </>} />
      <Card padding={0}>
        {!data ? <Loading /> : (
          <Table.ScrollContainer minWidth={900}>
            <Table>
              <Table.Thead><Table.Tr>
                <Table.Th>Event</Table.Th><Table.Th>Status</Table.Th><Table.Th>Intensity</Table.Th><Table.Th>Landfall</Table.Th>
                <Table.Th ta="right">Predicted</Table.Th><Table.Th ta="right">Tickets</Table.Th><Table.Th ta="right">Customers affected</Table.Th><Table.Th>Source</Table.Th><Table.Th>Created</Table.Th>
              </Table.Tr></Table.Thead>
              <Table.Tbody>{data.map(e => (
                <Table.Tr key={e.id} className="row-click" onClick={() => { setEventId(e.id); go(`/events/${e.id}`); }}>
                  <Table.Td><Text fw={600} size="sm">{e.name}</Text><Text size="xs" c="dimmed">{e.kind}</Text></Table.Td>
                  <Table.Td><EventStatusBadge status={e.status} /></Table.Td>
                  <Table.Td>Cat {e.category} · {e.max_wind_mph} mph</Table.Td>
                  <Table.Td>{dt(e.landfall_at)}</Table.Td>
                  <Table.Td ta="right" className="tabular">{fmt(e.predicted)}</Table.Td>
                  <Table.Td ta="right" className="tabular">{fmt(e.tickets)}</Table.Td>
                  <Table.Td ta="right" className="tabular">{fmt(e.customers_affected)}</Table.Td>
                  <Table.Td><Badge variant="outline" color={e.source === "nhc" ? "cyan" : "gray"}>{e.source === "nhc" ? "NHC" : "Manual"}</Badge></Table.Td>
                  <Table.Td><Text size="sm">{date(e.created_at)}</Text></Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
      <NewEventModal opened={newOpen} onClose={newCtl.close} onCreated={e => { setEventId(e.id); go(`/events/${e.id}`); }} />
      <NhcModal opened={nhcOpen} onClose={nhcCtl.close} onCreated={e => { setEventId(e.id); go(`/events/${e.id}`); }} />
    </>
  );
}

function NewEventModal({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (e: StormEvent) => void }) {
  const form = useForm({
    initialValues: { name: "", kind: "Hurricane", category: 2, max_wind_mph: 105, pressure_mb: 970, lat: 25.5, lng: -85.5, heading_deg: 30, speed_mph: 12, landfall_at: null as Date | null, notes: "" },
    validate: { name: (v: string) => (v.trim().length < 2 ? "Name the event" : null) },
  });
  const create = useAction((v: typeof form.values) => api.post<StormEvent>("/events", { ...v, landfall_at: v.landfall_at?.toISOString() ?? null }),
    { success: "Storm event created", invalidate: ["/events"] });
  return (
    <Modal opened={opened} onClose={onClose} title="New storm event" size="lg">
      <form onSubmit={form.onSubmit(async v => { const e = await create.mutateAsync(v); onClose(); form.reset(); onCreated(e); })}>
        <Stack>
          <Grid>
            <Grid.Col span={8}><TextInput label="Name" placeholder="Hurricane …" {...form.getInputProps("name")} /></Grid.Col>
            <Grid.Col span={4}><Select label="Type" data={["Hurricane", "Tropical Storm", "Tropical Depression", "Severe Thunderstorm", "Winter Storm"]} {...form.getInputProps("kind")} /></Grid.Col>
            <Grid.Col span={4}><NumberInput label="Forecast category" min={1} max={5} {...form.getInputProps("category")} /></Grid.Col>
            <Grid.Col span={4}><NumberInput label="Max wind (mph)" min={20} max={220} {...form.getInputProps("max_wind_mph")} /></Grid.Col>
            <Grid.Col span={4}><NumberInput label="Pressure (mb)" min={850} max={1030} {...form.getInputProps("pressure_mb")} /></Grid.Col>
            <Grid.Col span={3}><NumberInput label="Latitude" decimalScale={2} {...form.getInputProps("lat")} /></Grid.Col>
            <Grid.Col span={3}><NumberInput label="Longitude" decimalScale={2} {...form.getInputProps("lng")} /></Grid.Col>
            <Grid.Col span={3}><NumberInput label="Heading (°)" min={0} max={359} {...form.getInputProps("heading_deg")} /></Grid.Col>
            <Grid.Col span={3}><NumberInput label="Speed (mph)" min={0} max={60} {...form.getInputProps("speed_mph")} /></Grid.Col>
            <Grid.Col span={12}><DateTimePicker label="Expected landfall" placeholder="Optional" clearable valueFormat="ddd MMM D, h:mm A" {...form.getInputProps("landfall_at")} /></Grid.Col>
            <Grid.Col span={12}><Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} /></Grid.Col>
          </Grid>
          <Group justify="flex-end"><Button variant="default" onClick={onClose}>Cancel</Button><Button type="submit" loading={create.isPending}>Create event</Button></Group>
        </Stack>
      </form>
    </Modal>
  );
}

function NhcModal({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (e: StormEvent) => void }) {
  const { data, isFetching } = useGet<{ storms: NhcStorm[]; error: string | null; source: string }>(opened ? "/nhc/storms" : null);
  const imp = useAction((id: string) => api.post<StormEvent>("/events/import-nhc", { nhc_id: id }), { success: "Imported from the National Hurricane Center", invalidate: ["/events"] });
  return (
    <Modal opened={opened} onClose={onClose} title="Active storms — National Hurricane Center" size="xl">
      {isFetching && !data ? <Loading /> : data?.error ? <Alert color="red" icon={<IconAlertTriangle />}>{data.error}</Alert> : !data?.storms.length ? (
        <Empty title="No active storms right now" icon={<IconSatellite />}>The NHC feed has no active Atlantic or East Pacific systems. Create a planning event manually instead.</Empty>
      ) : (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Storm</Table.Th><Table.Th>Intensity</Table.Th><Table.Th>Position</Table.Th><Table.Th>Movement</Table.Th><Table.Th ta="right">To Tampa</Table.Th><Table.Th>Advisory</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>{data.storms.map(s => (
            <Table.Tr key={s.nhc_id}>
              <Table.Td><Text fw={600} size="sm">{s.name}</Text><Text size="xs" c="dimmed">{s.kind} · {s.nhc_id.toUpperCase()}</Text></Table.Td>
              <Table.Td>{s.category ? `Cat ${s.category} · ` : ""}{s.wind_mph} mph · {s.pressure_mb} mb</Table.Td>
              <Table.Td>{s.lat.toFixed(1)}°, {s.lng.toFixed(1)}°</Table.Td>
              <Table.Td>{s.movement}</Table.Td>
              <Table.Td ta="right">{fmt(s.distance_to_tampa_mi)} mi</Table.Td>
              <Table.Td><Text size="xs">{ago(s.updated_at)}</Text>{s.advisory_url && <Anchor href={s.advisory_url} target="_blank" size="xs">Read</Anchor>}</Table.Td>
              <Table.Td><Button size="compact-sm" leftSection={<IconCloudDownload size={14} />} loading={imp.isPending}
                onClick={async () => { const e = await imp.mutateAsync(s.nhc_id); onClose(); onCreated(e); }}>Track</Button></Table.Td>
            </Table.Tr>))}
          </Table.Tbody>
        </Table>
      )}
      <Text size="xs" c="dimmed" mt="sm">Source: {data?.source ?? "nhc.noaa.gov"} · live feed</Text>
    </Modal>
  );
}
