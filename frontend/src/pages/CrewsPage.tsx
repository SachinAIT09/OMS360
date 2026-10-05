import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Button, Card, Grid, Group, Menu, Modal, NumberInput, Progress, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { IconBuildingWarehouse, IconDots, IconHeartHandshake, IconPlus, IconSearch, IconTruck } from "@tabler/icons-react";
import { api, qs } from "../api/client";
import { useAction, useGet } from "../api/hooks";
import type { Crew, MutualAid, Yard } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { CrewStatusBadge, MutualAidBadge } from "../components/badges";
import { Empty, Loading, PageHeader, Stat } from "../components/common";
import { OutageDrawer } from "../components/OutageDrawer";
import { TerritoryMap } from "../components/TerritoryMap";
import { dt, fmt, label, money } from "../lib/format";

const CREW_COLOR: Record<string, string> = { available: "#3ec46d", staged: "#22b8cf", assigned: "#f5a623", working: "#2b6bff", off_shift: "#8a96c0" };
const MA_NEXT: Record<string, { to: string; label: string }[]> = {
  requested: [{ to: "confirmed", label: "Mark confirmed" }, { to: "cancelled", label: "Cancel request" }],
  confirmed: [{ to: "en_route", label: "Mark en route" }, { to: "cancelled", label: "Cancel request" }],
  en_route: [{ to: "arrived", label: "Check in at staging yard" }],
  arrived: [{ to: "released", label: "Release crews" }],
};

export default function CrewsPage() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState<string | null>("roster");
  return (
    <>
      <PageHeader title="Crews & mutual aid" description="Field workforce: in-house crews, mutual-aid partners and staging yards." />
      <Tabs value={tab} onChange={setTab} keepMounted={false}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="roster" leftSection={<IconTruck size={16} />}>Roster</Tabs.Tab>
          <Tabs.Tab value="mutual" leftSection={<IconHeartHandshake size={16} />}>Mutual aid</Tabs.Tab>
          <Tabs.Tab value="yards" leftSection={<IconBuildingWarehouse size={16} />}>Staging yards</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="roster"><Roster initialQ={params.get("q") ?? ""} /></Tabs.Panel>
        <Tabs.Panel value="mutual"><MutualAidTab /></Tabs.Panel>
        <Tabs.Panel value="yards"><Yards /></Tabs.Panel>
      </Tabs>
    </>
  );
}

function Roster({ initialQ }: { initialQ: string }) {
  const { can } = useAuth();
  const [q, setQ] = useState(initialQ);
  const [dq] = useDebouncedValue(q, 300);
  const [status, setStatus] = useState<string | null>(null);
  const [kind, setKind] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [ticket, setTicket] = useState<number | null>(null);
  const { data } = useGet<Crew[]>(`/crews${qs({ q: dq, status, kind, source })}`);
  const all = useGet<Crew[]>("/crews");
  const setCrew = useAction(({ id, st }: { id: number; st: string }) => api.patch(`/crews/${id}`, { status: st }), { success: "Crew updated" });
  const counts = (all.data ?? []).reduce<Record<string, number>>((m, c) => ({ ...m, [c.status]: (m[c.status] ?? 0) + 1 }), {});
  const workers = (all.data ?? []).filter(c => c.kind === "line").reduce((s, c) => s + c.size, 0);

  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, md: 5 }}>
        <Stat label="Line workers" value={fmt(workers)} hint={`${(all.data ?? []).filter(c => c.source === "mutual_aid").length} mutual-aid crews`} />
        <Stat label="Available" value={counts.available ?? 0} color="teal" />
        <Stat label="Staged" value={counts.staged ?? 0} color="cyan" />
        <Stat label="Assigned / working" value={(counts.assigned ?? 0) + (counts.working ?? 0)} color="blue" />
        <Stat label="Off shift" value={counts.off_shift ?? 0} color="gray" />
      </SimpleGrid>
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, xl: 7 }}>
          <Card padding={0}>
            <Group p="sm" gap="sm">
              <TextInput placeholder="Crew code, company, foreman" leftSection={<IconSearch size={16} />} value={q} onChange={e => setQ(e.currentTarget.value)} w={240} />
              <Select placeholder="Status" clearable w={140} value={status} onChange={setStatus} data={["available", "staged", "assigned", "working", "off_shift"].map(s => ({ value: s, label: label(s) }))} />
              <Select placeholder="Type" clearable w={130} value={kind} onChange={setKind} data={[{ value: "line", label: "Line" }, { value: "tree", label: "Tree" }, { value: "assessment", label: "Assessment" }]} />
              <Select placeholder="Source" clearable w={140} value={source} onChange={setSource} data={[{ value: "internal", label: "In-house" }, { value: "mutual_aid", label: "Mutual aid" }]} />
              <Text size="sm" c="dimmed" ml="auto">{data?.length ?? 0} crews</Text>
            </Group>
            {!data ? <Loading /> : (
              <Table.ScrollContainer minWidth={760} mah={560}>
                <Table stickyHeader>
                  <Table.Thead><Table.Tr><Table.Th>Crew</Table.Th><Table.Th>Type</Table.Th><Table.Th>Company</Table.Th><Table.Th ta="right">Size</Table.Th><Table.Th>Status</Table.Th><Table.Th>Current work</Table.Th><Table.Th /></Table.Tr></Table.Thead>
                  <Table.Tbody>{data.slice(0, 300).map(c => (
                    <Table.Tr key={c.id}>
                      <Table.Td><Text size="sm" fw={600}>{c.code}</Text><Text size="xs" c="dimmed">{c.lead}</Text></Table.Td>
                      <Table.Td>{label(c.kind)}</Table.Td>
                      <Table.Td><Text size="sm">{c.company}</Text>{c.source === "mutual_aid" && <Badge size="xs" color="ai" variant="outline">mutual aid</Badge>}</Table.Td>
                      <Table.Td ta="right">{c.size}</Table.Td>
                      <Table.Td><CrewStatusBadge status={c.status} size="sm" /></Table.Td>
                      <Table.Td>{c.current ? <Button size="compact-xs" variant="subtle" onClick={() => setTicket(c.current!.id)}>{c.current.number}</Button> : <Text size="xs" c="dimmed">—</Text>}</Table.Td>
                      <Table.Td>{can("crews.manage") && !["assigned", "working"].includes(c.status) && (
                        <Menu position="bottom-end"><Menu.Target><Button size="compact-xs" variant="subtle" color="gray"><IconDots size={14} /></Button></Menu.Target>
                          <Menu.Dropdown>
                            {c.status !== "available" && <Menu.Item onClick={() => setCrew.mutate({ id: c.id, st: "available" })}>Set available</Menu.Item>}
                            {c.status !== "off_shift" && <Menu.Item onClick={() => setCrew.mutate({ id: c.id, st: "off_shift" })}>Send off shift (rest)</Menu.Item>}
                          </Menu.Dropdown></Menu>)}
                      </Table.Td>
                    </Table.Tr>))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, xl: 5 }}>
          <Card padding="sm">
            <TerritoryMap height={560} pins={(data ?? []).filter(c => c.status !== "released").slice(0, 400).map(c => ({ id: c.id, lat: c.lat, lng: c.lng, color: CREW_COLOR[c.status] ?? "#8a96c0",
              popup: <div><b>{c.code}</b> · {c.company}<br />{label(c.kind)} crew, {c.size} workers<br />{label(c.status)}{c.current ? ` — ${c.current.number}` : ""}</div> }))} />
            <Group gap="md" mt="xs">{Object.entries(CREW_COLOR).map(([s, col]) => <Group key={s} gap={4}><span className="pin" style={{ background: col, display: "inline-block" }} /><Text size="xs">{label(s)}</Text></Group>)}</Group>
          </Card>
        </Grid.Col>
      </Grid>
      <OutageDrawer id={ticket} onClose={() => setTicket(null)} />
    </Stack>
  );
}

function MutualAidTab() {
  const { event } = useCurrentEvent();
  const { can } = useAuth();
  const { data } = useGet<MutualAid[]>(event ? `/mutual-aid?event_id=${event.id}` : null);
  const [open, ctl] = useDisclosure(false);
  const move = useAction(({ id, to }: { id: number; to: string }) => api.post(`/mutual-aid/${id}/status`, { status: to }), { success: "Mutual-aid request updated" });
  if (!event) return <Empty title="Select a storm event" />;
  const active = (data ?? []).filter(r => !["cancelled", "released"].includes(r.status));
  const workers = active.reduce((s, r) => s + r.workers, 0);
  const arrived = active.filter(r => r.status === "arrived").reduce((s, r) => s + r.workers, 0);
  const daily = active.reduce((s, r) => s + r.workers * r.cost_per_worker_day, 0);
  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <Stat label="Workers requested" value={fmt(workers)} hint={`${active.length} active requests`} />
        <Stat label="Arrived" value={fmt(arrived)} color="teal" progress={workers ? arrived / workers : 0} />
        <Stat label="Daily cost" value={money(daily)} hint="incl. lodging & per diem" />
        <Stat label="Partners" value={new Set(active.map(r => r.company)).size} />
      </SimpleGrid>
      <Card padding={0}>
        <Group p="sm" justify="space-between"><Text fw={600}>Requests for {event.name}</Text>
          {can("mutual_aid.manage") && event.status !== "closed" && <Button size="sm" leftSection={<IconPlus size={16} />} onClick={ctl.open}>New request</Button>}</Group>
        {!data ? <Loading /> : !data.length ? <Empty title="No mutual aid requested">Approve the mutual-aid recommendation on the Overview, or create a request.</Empty> : (
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Partner</Table.Th><Table.Th>Type</Table.Th><Table.Th ta="right">Workers</Table.Th><Table.Th>Status</Table.Th><Table.Th>ETA</Table.Th><Table.Th>Requested</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>{data.map(r => (
              <Table.Tr key={r.id}>
                <Table.Td><Text size="sm" fw={600}>{r.company}</Text><Text size="xs" c="dimmed">{r.origin}</Text></Table.Td>
                <Table.Td>{label(r.kind)}</Table.Td><Table.Td ta="right" className="tabular">{fmt(r.workers)}</Table.Td>
                <Table.Td><MutualAidBadge status={r.status} /></Table.Td>
                <Table.Td>{r.status === "arrived" ? `Arrived ${dt(r.arrived_at)}` : dt(r.eta)}</Table.Td>
                <Table.Td><Text size="sm">{dt(r.requested_at)}</Text><Text size="xs" c="dimmed">{r.requested_by}</Text></Table.Td>
                <Table.Td>{can("mutual_aid.manage") && MA_NEXT[r.status] && (
                  <Menu position="bottom-end"><Menu.Target><Button size="compact-sm" variant="default">Update</Button></Menu.Target>
                    <Menu.Dropdown>{MA_NEXT[r.status].map(n => <Menu.Item key={n.to} color={n.to === "cancelled" ? "red" : undefined} onClick={() => move.mutate({ id: r.id, to: n.to })}>{n.label}</Menu.Item>)}</Menu.Dropdown>
                  </Menu>)}</Table.Td>
              </Table.Tr>))}
            </Table.Tbody>
          </Table>
        )}
      </Card>
      <NewRequest opened={open} onClose={ctl.close} eventId={event.id} />
    </Stack>
  );
}

function NewRequest({ opened, onClose, eventId }: { opened: boolean; onClose: () => void; eventId: number }) {
  const form = useForm({ initialValues: { company: "", origin: "", kind: "line", workers: 40, eta: null as Date | null },
    validate: { company: (v: string) => (v.trim().length > 1 ? null : "Partner utility or contractor") } });
  const create = useAction((v: typeof form.values) => api.post("/mutual-aid", { ...v, event_id: eventId, eta: v.eta?.toISOString() ?? null }), { success: "Mutual-aid request sent" });
  return (
    <Modal opened={opened} onClose={onClose} title="Request mutual aid">
      <form onSubmit={form.onSubmit(async v => { await create.mutateAsync(v); onClose(); form.reset(); })}>
        <Stack>
          <TextInput label="Partner" placeholder="e.g. Southern Grid Cooperative" {...form.getInputProps("company")} />
          <TextInput label="Origin" placeholder="State" {...form.getInputProps("origin")} />
          <Group grow>
            <Select label="Crew type" data={[{ value: "line", label: "Line" }, { value: "tree", label: "Tree" }, { value: "assessment", label: "Damage assessment" }]} {...form.getInputProps("kind")} />
            <NumberInput label="Workers" min={2} max={2000} {...form.getInputProps("workers")} />
          </Group>
          <DateTimePicker label="Requested arrival" clearable valueFormat="ddd MMM D, h:mm A" {...form.getInputProps("eta")} />
          <Group justify="flex-end"><Button variant="default" onClick={onClose}>Cancel</Button><Button type="submit" loading={create.isPending}>Send request</Button></Group>
        </Stack>
      </form>
    </Modal>
  );
}

function Yards() {
  const { data } = useGet<Yard[]>("/staging-yards");
  if (!data) return <Loading />;
  return (
    <Grid gutter="lg">
      <Grid.Col span={{ base: 12, lg: 6 }}>
        <Card padding={0}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Yard</Table.Th><Table.Th>Status</Table.Th><Table.Th ta="right">Staged workers</Table.Th><Table.Th w={160}>Capacity used</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{data.map(y => (
              <Table.Tr key={y.id}><Table.Td>{y.name}</Table.Td><Table.Td><Badge color={y.active ? "teal" : "gray"}>{y.active ? "Open" : "Closed"}</Badge></Table.Td>
                <Table.Td ta="right">{fmt(y.staged_workers)} / {fmt(y.capacity)}</Table.Td>
                <Table.Td><Progress value={((y.staged_workers ?? 0) / y.capacity) * 100} size="sm" /></Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed" p="sm">All yards sit outside storm-surge zones A/B and within 25 minutes of the highest-impact zones.</Text>
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 6 }}><Card padding="sm"><TerritoryMap height={400} yards={data} /></Card></Grid.Col>
    </Grid>
  );
}
