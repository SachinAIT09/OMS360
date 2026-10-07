import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Badge, Button, Card, Group, Modal, MultiSelect, NumberInput, Pagination, SegmentedControl, Select, Stack, Table, Text, TextInput, Textarea, UnstyledButton,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { IconArrowsSort, IconBolt, IconDownload, IconMap, IconPlus, IconSearch, IconTable, IconWand } from "@tabler/icons-react";
import { API_BASE, api, qs, tokenStore } from "../api/client";
import { useAction, useGet, useReference } from "../api/hooks";
import type { Outage, Page } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { OutageStatusBadge, PriorityBadge } from "../components/badges";
import { Empty, Loading, PageHeader } from "../components/common";
import { OutageDrawer } from "../components/OutageDrawer";
import { TerritoryMap } from "../components/TerritoryMap";
import { ago, dtShort, fmt, label } from "../lib/format";

const STATUSES = ["reported", "assessed", "assigned", "in_progress", "restored", "cancelled"];
const STATUS_COLOR: Record<string, string> = { reported: "#e0506a", assessed: "#f07a2e", assigned: "#f5a623", in_progress: "#2b6bff", restored: "#3ec46d", cancelled: "#8a96c0" };

export default function OutagesPage() {
  const { event } = useCurrentEvent();
  const { can } = useAuth();
  const ref = useReference();
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState<string[]>(params.get("status")?.split(",") ?? ["reported", "assessed", "assigned", "in_progress"]);
  const [priority, setPriority] = useState<string | null>(params.get("priority"));
  const [zone, setZone] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [dq] = useDebouncedValue(q, 300);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ col: string; desc: boolean }>({ col: "priority", desc: true });
  const [view, setView] = useState(params.get("view") ?? "table");
  const [openId, setOpenId] = useState<number | null>(Number(params.get("open")) || null);
  const [newOpen, newCtl] = useDisclosure(false);

  useEffect(() => setPage(1), [status, priority, zone, dq, event?.id]);
  const size = view === "map" ? 500 : 25;
  const path = event ? `/outages${qs({ event_id: event.id, status: status.join(","), priority, zone, q: dq, page: view === "map" ? 1 : page, size, sort: sort.col, desc: sort.desc })}` : null;
  const { data, isLoading } = useGet<Page<Outage>>(path);
  const dispatch = useAction(() => api.post<{ dispatched: number }>(`/events/${event!.id}/auto-dispatch`), { success: r => `${r.dispatched} tickets dispatched to the nearest idle crews` });

  const exportCsv = async () => {
    const res = await fetch(`${API_BASE}/outages/export.csv?event_id=${event!.id}`, { headers: { Authorization: `Bearer ${tokenStore.get()}` } });
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a"); a.href = url; a.download = `outages-${event!.name.replace(/\s+/g, "-")}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  const th = (col: string, text: string, right = false) => (
    <Table.Th ta={right ? "right" : undefined}>
      <UnstyledButton onClick={() => setSort(s => ({ col, desc: s.col === col ? !s.desc : true }))}>
        <Group gap={4} justify={right ? "flex-end" : undefined}><Text size="sm" fw={600}>{text}</Text><IconArrowsSort size={12} opacity={sort.col === col ? 1 : 0.35} /></Group>
      </UnstyledButton>
    </Table.Th>
  );

  if (!event) return <Empty title="Select a storm event" />;
  return (
    <>
      <PageHeader title="Outages" description={`Outage tickets for ${event.name} — from smart meters (AMI), SCADA, customers and field crews.`}
        actions={<>
          <Button variant="default" leftSection={<IconDownload size={16} />} onClick={exportCsv}>Export CSV</Button>
          {can("outages.manage") && <Button variant="light" color="ai" leftSection={<IconWand size={16} />} loading={dispatch.isPending} onClick={() => dispatch.mutate()}>Auto-dispatch</Button>}
          {can("outages.manage") && <Button leftSection={<IconPlus size={16} />} onClick={newCtl.open}>New ticket</Button>}
        </>} />
      <Card mb="md" padding="sm">
        <Group gap="sm" wrap="wrap">
          <TextInput placeholder="Ticket, feeder or device" leftSection={<IconSearch size={16} />} value={q} onChange={e => setQ(e.currentTarget.value)} w={230} />
          <MultiSelect placeholder="Status" data={STATUSES.map(s => ({ value: s, label: label(s) }))} value={status} onChange={setStatus} clearable w={330} />
          <Select placeholder="Priority" data={[{ value: "critical", label: "Critical" }, { value: "high", label: "High" }, { value: "normal", label: "Normal" }]} value={priority} onChange={setPriority} clearable w={140} />
          <Select placeholder="Zone" data={(ref.data?.zones ?? []).map(z => ({ value: z.id, label: z.short }))} value={zone} onChange={setZone} clearable searchable w={180} />
          <div style={{ flex: 1 }} />
          <Badge variant="light" color="gray" size="lg" radius="sm" tt="none" fw={500}>{fmt(data?.total)} tickets</Badge>
          <SegmentedControl size="sm" radius="md" value={view} onChange={v => { setView(v); setParams(v === "map" ? { view: v } : {}); }}
            data={[
              { value: "table", label: <span className="seg-label"><IconTable size={15} stroke={1.8} />Table</span> },
              { value: "map", label: <span className="seg-label"><IconMap size={15} stroke={1.8} />Map</span> },
            ]} />
        </Group>
      </Card>

      {isLoading || !data ? <Loading /> : !data.items.length ? (
        <Card><Empty title="No outages match these filters" icon={<IconBolt />}>{event.status === "active" ? "New tickets arrive automatically from the OMS/AMI feed." : "Tickets are created once the event is active."}</Empty></Card>
      ) : view === "map" ? (
        <Card padding="sm">
          <TerritoryMap height={620} facilities={ref.data?.facilities} pins={data.items.map(o => ({ id: o.id, lat: o.lat, lng: o.lng, color: STATUS_COLOR[o.status], onClick: () => setOpenId(o.id) }))} />
          <Group gap="md" mt="xs">{STATUSES.slice(0, 5).map(s => <Group key={s} gap={4}><span className="pin" style={{ background: STATUS_COLOR[s], display: "inline-block" }} /><Text size="xs">{label(s)}</Text></Group>)}</Group>
        </Card>
      ) : (
        <Card padding={0}>
          <Table.ScrollContainer minWidth={1100}>
            <Table>
              <Table.Thead><Table.Tr>
                {th("number", "Ticket")}{th("priority", "Priority")}{th("status", "Status")}{th("zone", "Zone / feeder")}<Table.Th>Cause</Table.Th>
                {th("customers", "Customers", true)}<Table.Th>Crew</Table.Th><Table.Th>ETR</Table.Th>{th("reported_at", "Reported")}
              </Table.Tr></Table.Thead>
              <Table.Tbody>{data.items.map(o => (
                <Table.Tr key={o.id} className="row-click" onClick={() => setOpenId(o.id)}>
                  <Table.Td><Text fw={600} size="sm">{o.number}</Text><Text size="xs" c="dimmed">{o.source}</Text></Table.Td>
                  <Table.Td><PriorityBadge priority={o.priority} size="sm" /></Table.Td>
                  <Table.Td><OutageStatusBadge status={o.status} size="sm" /></Table.Td>
                  <Table.Td><Text size="sm">{o.zone}</Text><Text size="xs" c="dimmed">{o.feeder_id}</Text></Table.Td>
                  <Table.Td><Text size="sm">{label(o.cause)}</Text><Text size="xs" c="dimmed">{label(o.damage)}</Text></Table.Td>
                  <Table.Td ta="right" className="tabular" fw={500}>{fmt(o.customers)}</Table.Td>
                  <Table.Td>{o.crew ? <Badge variant="outline" color="blue">{o.crew.code}</Badge> : <Text size="xs" c="dimmed">Unassigned</Text>}</Table.Td>
                  <Table.Td>{o.status === "restored" ? <Text size="sm" c="teal">Restored {dtShort(o.restored_at)}</Text> :
                    <><Text size="sm">{dtShort(o.etr_at)}</Text><Text size="xs" c="dimmed">{o.etr_committed ? (o.etr_override ? "manual" : "committed") : "AI estimate"}</Text></>}</Table.Td>
                  <Table.Td><Text size="sm">{ago(o.reported_at)}</Text></Table.Td>
                </Table.Tr>))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group justify="center" p="sm"><Pagination total={Math.ceil(data.total / size)} value={page} onChange={setPage} size="sm" /></Group>
        </Card>
      )}
      <OutageDrawer id={openId} onClose={() => { setOpenId(null); if (params.get("open")) setParams({}); }} />
      <NewTicketModal opened={newOpen} onClose={newCtl.close} eventId={event.id} />
    </>
  );
}

function NewTicketModal({ opened, onClose, eventId }: { opened: boolean; onClose: () => void; eventId: number }) {
  const ref = useReference();
  const form = useForm({
    initialValues: { zone_id: "", feeder_id: "", device: "", cause: "unknown", damage: "unknown", customers: 1, priority: "normal", notes: "" },
    validate: { zone_id: (v: string) => (v ? null : "Choose a zone"), feeder_id: (v: string) => (v ? null : "Choose a feeder") },
  });
  const create = useAction((v: typeof form.values) => api.post("/outages", { ...v, event_id: eventId }), { success: "Outage ticket created" });
  const feeders = (ref.data?.feeders ?? []).filter(f => f.zone_id === form.values.zone_id).map(f => f.id);
  return (
    <Modal opened={opened} onClose={onClose} title="New outage ticket" size="lg">
      <form onSubmit={form.onSubmit(async v => { await create.mutateAsync(v); onClose(); form.reset(); })}>
        <Stack>
          <Group grow>
            <Select label="Zone" searchable data={(ref.data?.zones ?? []).map(z => ({ value: z.id, label: z.short }))} {...form.getInputProps("zone_id")}
              onChange={v => { form.setFieldValue("zone_id", v ?? ""); form.setFieldValue("feeder_id", ""); }} />
            <Select label="Feeder" searchable data={feeders} disabled={!form.values.zone_id} {...form.getInputProps("feeder_id")} />
          </Group>
          <Group grow>
            <TextInput label="Device" placeholder="e.g. Transformer T-4471" {...form.getInputProps("device")} />
            <NumberInput label="Customers affected" min={1} max={100000} thousandSeparator {...form.getInputProps("customers")} />
          </Group>
          <Group grow>
            <Select label="Cause" data={["wind", "tree", "surge", "flooding", "equipment", "unknown"].map(c => ({ value: c, label: label(c) }))} {...form.getInputProps("cause")} />
            <Select label="Damage" data={["service", "conductor", "transformer", "pole", "unknown"].map(c => ({ value: c, label: label(c) }))} {...form.getInputProps("damage")} />
            <Select label="Priority" data={["critical", "high", "normal"].map(c => ({ value: c, label: label(c) }))} {...form.getInputProps("priority")} />
          </Group>
          <Textarea label="Notes" autosize minRows={2} {...form.getInputProps("notes")} />
          <Group justify="flex-end"><Button variant="default" onClick={onClose}>Cancel</Button><Button type="submit" loading={create.isPending}>Create ticket</Button></Group>
        </Stack>
      </form>
    </Modal>
  );
}
