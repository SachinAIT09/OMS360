import { useNavigate } from "react-router-dom";
import { Alert, Anchor, Badge, Button, Card, Grid, Group, Modal, NumberInput, Select, Stack, Table, Text, Textarea, TextInput } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { IconAlertTriangle, IconCloudDownload, IconPlus, IconSatellite, IconTornado } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet } from "../api/hooks";
import { EVENT_KINDS, type NhcStorm, type NwsAlert, type StormEvent } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { EventStatusBadge } from "../components/badges";
import { Empty, Loading, PageHeader } from "../components/common";
import { ago, date, dt, fmt, intensity, isRain, isTornado } from "../lib/format";
import { PROFILE } from "../lib/profile";

export default function EventsPage() {
  const { can } = useAuth();
  const go = useNavigate();
  const { setEventId } = useCurrentEvent();
  const { data } = useGet<StormEvent[]>("/events");
  const [newOpen, newCtl] = useDisclosure(false);
  const [nhcOpen, nhcCtl] = useDisclosure(false);
  const [nwsOpen, nwsCtl] = useDisclosure(false);

  return (
    <>
      <PageHeader title="Storm events" description="Every storm the utility prepares for, responds to and reports on."
        actions={can("events.manage") && <>
          <Button variant="default" leftSection={<IconTornado size={16} />} onClick={nwsCtl.open}>NWS warnings</Button>
          {PROFILE.hazard === "hurricane" && <Button variant="default" leftSection={<IconSatellite size={16} />} onClick={nhcCtl.open}>Import from NHC</Button>}
          <Button leftSection={<IconPlus size={16} />} onClick={newCtl.open}>New event</Button>
        </>} />
      <Card padding={0}>
        {!data ? <Loading /> : (
          <Table.ScrollContainer minWidth={900}>
            <Table>
              <Table.Thead><Table.Tr>
                <Table.Th>Event</Table.Th><Table.Th>Status</Table.Th><Table.Th>Intensity</Table.Th><Table.Th>{PROFILE.hazard === "tornado" ? "Touchdown / onset" : "Landfall / onset"}</Table.Th>
                <Table.Th ta="right">Predicted</Table.Th><Table.Th ta="right">Tickets</Table.Th><Table.Th ta="right">Customers affected</Table.Th><Table.Th>Source</Table.Th><Table.Th>Created</Table.Th>
              </Table.Tr></Table.Thead>
              <Table.Tbody>{data.map(e => (
                <Table.Tr key={e.id} className="row-click" onClick={() => { setEventId(e.id); go(`/events/${e.id}`); }}>
                  <Table.Td><Text fw={600} size="sm">{e.name}</Text><Text size="xs" c="dimmed">{e.kind}</Text></Table.Td>
                  <Table.Td><EventStatusBadge status={e.status} /></Table.Td>
                  <Table.Td>{intensity(e)}</Table.Td>
                  <Table.Td>{dt(e.landfall_at)}</Table.Td>
                  <Table.Td ta="right" className="tabular">{fmt(e.predicted)}</Table.Td>
                  <Table.Td ta="right" className="tabular">{fmt(e.tickets)}</Table.Td>
                  <Table.Td ta="right" className="tabular">{fmt(e.customers_affected)}</Table.Td>
                  <Table.Td><Badge variant="outline" color={e.source === "nhc" ? "cyan" : e.source === "nws" ? "red" : "gray"}>{e.source === "nhc" ? "NHC" : e.source === "nws" ? "NWS" : "Manual"}</Badge></Table.Td>
                  <Table.Td><Text size="sm">{date(e.created_at)}</Text></Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>
      <NewEventModal opened={newOpen} onClose={newCtl.close} onCreated={e => { setEventId(e.id); go(`/events/${e.id}`); }} />
      <NhcModal opened={nhcOpen} onClose={nhcCtl.close} onCreated={e => { setEventId(e.id); go(`/events/${e.id}`); }} />
      <NwsModal opened={nwsOpen} onClose={nwsCtl.close} onCreated={e => { setEventId(e.id); go(`/events/${e.id}?tab=prediction`); }} />
    </>
  );
}

function NewEventModal({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (e: StormEvent) => void }) {
  const form = useForm({
    initialValues: { name: "", kind: PROFILE.new_event.kind, category: PROFILE.hazard === "tornado" ? 3 : 2, max_wind_mph: PROFILE.hazard === "tornado" ? 150 : 105,
      pressure_mb: 970, lat: PROFILE.new_event.lat, lng: PROFILE.new_event.lng, heading_deg: PROFILE.hazard === "tornado" ? 45 : 30,
      speed_mph: PROFILE.hazard === "tornado" ? 30 : 12, landfall_at: null as Date | null, notes: "",
      rain_total_in: 4, rain_rate_in_hr: 1, duration_h: 12, soil_saturation: 50, path_length_mi: 15, path_width_m: 800 },
    validate: { name: (v: string) => (v.trim().length < 2 ? "Name the event" : null) },
  });
  const rain = isRain(form.values);
  const tornado = isTornado(form.values);
  const create = useAction((v: typeof form.values) => api.post<StormEvent>("/events", {
    ...v, landfall_at: v.landfall_at?.toISOString() ?? null,
    ...(isRain(v) ? { soil_saturation: v.soil_saturation / 100 } : { rain_total_in: null, rain_rate_in_hr: null, duration_h: null, soil_saturation: null }),
    ...(isTornado(v) ? {} : { path_length_mi: null, path_width_m: null }),
  }),
    { success: "Storm event created", invalidate: ["/events"] });
  return (
    <Modal opened={opened} onClose={onClose} title="New storm event" size="lg">
      <form onSubmit={form.onSubmit(async v => { const e = await create.mutateAsync(v); onClose(); form.reset(); onCreated(e); })}>
        <Stack>
          <Grid>
            <Grid.Col span={8}><TextInput label="Name" placeholder={rain ? "October Rain Event" : tornado ? "Central Oklahoma tornado outbreak" : "Hurricane …"} {...form.getInputProps("name")} /></Grid.Col>
            <Grid.Col span={4}><Select label="Type" data={[...EVENT_KINDS]} allowDeselect={false} {...form.getInputProps("kind")} /></Grid.Col>
            {rain ? <>
              <Grid.Col span={3}><NumberInput label="Rainfall (in)" min={0.5} max={40} decimalScale={1} {...form.getInputProps("rain_total_in")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Peak rate (in/hr)" min={0.1} max={8} decimalScale={1} step={0.25} {...form.getInputProps("rain_rate_in_hr")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Duration (h)" min={1} max={240} {...form.getInputProps("duration_h")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Soil saturation" min={0} max={100} suffix="%" {...form.getInputProps("soil_saturation")} /></Grid.Col>
              <Grid.Col span={12}><DateTimePicker label="Rain onset" placeholder="Optional" clearable valueFormat="ddd MMM D, h:mm A" {...form.getInputProps("landfall_at")} /></Grid.Col>
            </> : tornado ? <>
              <Grid.Col span={4}><NumberInput label="EF rating" min={0} max={5} {...form.getInputProps("category")} /></Grid.Col>
              <Grid.Col span={4}><NumberInput label="Peak gust (mph)" min={65} max={220} {...form.getInputProps("max_wind_mph")} /></Grid.Col>
              <Grid.Col span={4}><NumberInput label="Damage width (m)" min={30} max={4000} step={50} {...form.getInputProps("path_width_m")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Touchdown latitude" decimalScale={3} {...form.getInputProps("lat")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Touchdown longitude" decimalScale={3} {...form.getInputProps("lng")} /></Grid.Col>
              <Grid.Col span={2}><NumberInput label="Heading (°)" min={0} max={359} {...form.getInputProps("heading_deg")} /></Grid.Col>
              <Grid.Col span={2}><NumberInput label="Length (mi)" min={0.5} max={200} decimalScale={1} {...form.getInputProps("path_length_mi")} /></Grid.Col>
              <Grid.Col span={2}><NumberInput label="Speed (mph)" min={5} max={70} {...form.getInputProps("speed_mph")} /></Grid.Col>
              <Grid.Col span={12}><DateTimePicker label="Expected touchdown" placeholder="Optional" clearable valueFormat="ddd MMM D, h:mm A" {...form.getInputProps("landfall_at")} /></Grid.Col>
              <Grid.Col span={12}><Text size="xs" c="dimmed">The damage path runs from the touchdown point along the heading. The prediction matches it against every circuit's route,
                so circuits it crosses are planned as rebuilds.</Text></Grid.Col>
            </> : <>
              <Grid.Col span={4}><NumberInput label="Forecast category" min={1} max={5} {...form.getInputProps("category")} /></Grid.Col>
              <Grid.Col span={4}><NumberInput label="Max wind (mph)" min={20} max={220} {...form.getInputProps("max_wind_mph")} /></Grid.Col>
              <Grid.Col span={4}><NumberInput label="Pressure (mb)" min={850} max={1030} {...form.getInputProps("pressure_mb")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Latitude" decimalScale={2} {...form.getInputProps("lat")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Longitude" decimalScale={2} {...form.getInputProps("lng")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Heading (°)" min={0} max={359} {...form.getInputProps("heading_deg")} /></Grid.Col>
              <Grid.Col span={3}><NumberInput label="Speed (mph)" min={0} max={60} {...form.getInputProps("speed_mph")} /></Grid.Col>
              <Grid.Col span={12}><DateTimePicker label="Expected landfall" placeholder="Optional" clearable valueFormat="ddd MMM D, h:mm A" {...form.getInputProps("landfall_at")} /></Grid.Col>
            </>}
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
          <Table.Thead><Table.Tr><Table.Th>Storm</Table.Th><Table.Th>Intensity</Table.Th><Table.Th>Position</Table.Th><Table.Th>Movement</Table.Th><Table.Th ta="right">To {PROFILE.weather_label}</Table.Th><Table.Th>Advisory</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>{data.storms.map(s => (
            <Table.Tr key={s.nhc_id}>
              <Table.Td><Text fw={600} size="sm">{s.name}</Text><Text size="xs" c="dimmed">{s.kind} · {s.nhc_id.toUpperCase()}</Text></Table.Td>
              <Table.Td>{s.category ? `Cat ${s.category} · ` : ""}{s.wind_mph} mph · {s.pressure_mb} mb</Table.Td>
              <Table.Td>{s.lat.toFixed(1)}°, {s.lng.toFixed(1)}°</Table.Td>
              <Table.Td>{s.movement}</Table.Td>
              <Table.Td ta="right">{fmt(s.distance_mi)} mi</Table.Td>
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

const ALERT_COLOR: Record<string, string> = { "Tornado Emergency": "grape", "Tornado Warning": "red", "Tornado Watch": "yellow",
  "Severe Thunderstorm Warning": "orange", "Severe Thunderstorm Watch": "gray" };

/** Active NWS tornado / severe-thunderstorm alerts for the territory's state; a tornado warning can be tracked as an event. */
function NwsModal({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (e: StormEvent) => void }) {
  const { data, isFetching } = useGet<{ alerts: NwsAlert[]; error: string | null; source: string }>(opened ? "/nws/alerts" : null);
  const imp = useAction((body: object) => api.post<StormEvent>("/events/import-nws", body),
    { success: "Tornado warning imported — planning path projected and prediction run", invalidate: ["/events"] });
  const track = async (body: object) => { const e = await imp.mutateAsync(body); onClose(); onCreated(e); };
  return (
    <Modal opened={opened} onClose={onClose} title={`Active alerts — National Weather Service (${PROFILE.state || "territory"})`} size="xl">
      {isFetching && !data ? <Loading /> : data?.error ? <Alert color="red" icon={<IconAlertTriangle />}>{data.error}</Alert> : !data?.alerts.length ? (
        <Empty title="No tornado or severe-thunderstorm alerts right now" icon={<IconTornado />}>
          When a tornado warning is issued, track it here: OMS360 projects a planning damage path along the storm's motion and predicts which circuits it hits.
          <Button mt="md" variant="light" loading={imp.isPending} onClick={() => track({ sample: true })}>Load a sample tornado warning (sandbox)</Button>
        </Empty>
      ) : (
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Alert</Table.Th><Table.Th>Area</Table.Th><Table.Th>Tornado</Table.Th><Table.Th>Motion</Table.Th><Table.Th>Expires</Table.Th><Table.Th /></Table.Tr></Table.Thead>
          <Table.Tbody>{data.alerts.map(a => (
            <Table.Tr key={a.id}>
              <Table.Td><Badge color={ALERT_COLOR[a.event] ?? "gray"}>{a.event}</Badge><Text size="xs" c="dimmed" mt={4} maw={260}>{a.headline}</Text></Table.Td>
              <Table.Td><Text size="xs" maw={220}>{a.area}</Text></Table.Td>
              <Table.Td><Text size="xs">{a.detection || "—"}{a.damage_threat && ` · ${a.damage_threat}`}</Text>
                {a.ef_estimate != null && <Text size="xs" c="dimmed">plan as EF{a.ef_estimate}</Text>}</Table.Td>
              <Table.Td><Text size="xs">{a.motion ? `${a.motion.speed_mph} mph toward ${Math.round(a.motion.heading_deg)}°` : "—"}</Text></Table.Td>
              <Table.Td><Text size="xs">{dt(a.expires)}</Text></Table.Td>
              <Table.Td>{a.importable && <Button size="compact-sm" leftSection={<IconCloudDownload size={14} />} loading={imp.isPending}
                onClick={() => track({ alert_id: a.id })}>Track</Button>}</Table.Td>
            </Table.Tr>))}
          </Table.Tbody>
        </Table>
      )}
      <Text size="xs" c="dimmed" mt="sm">Source: {data?.source ?? "api.weather.gov"} · live feed. The planning EF rating comes from the warning's tags (observed tornado,
        considerable / catastrophic damage threat); replace the path with the NWS damage survey afterwards on the event's Storm tab.</Text>
    </Modal>
  );
}
