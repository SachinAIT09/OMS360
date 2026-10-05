import { useState } from "react";
import { Alert, Badge, Button, Divider, Drawer, Grid, Group, Loader, Select, SimpleGrid, Stack, Text, Textarea, Timeline, Title } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { IconAlertTriangle, IconBuildingHospital, IconClock, IconPlayerPlay, IconCheck, IconUserCheck } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet } from "../api/hooks";
import type { Crew, OutageDetail } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ago, dt, fmt, label } from "../lib/format";
import { OutageStatusBadge, PriorityBadge } from "./badges";

const CAUSES = ["wind", "tree", "surge", "flooding", "equipment", "unknown"];
const DAMAGE = ["service", "conductor", "transformer", "pole", "none", "unknown"];

export function OutageDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  return (
    <Drawer opened={id != null} onClose={onClose} title={null} size={560} padding="lg">
      {id != null && <Body id={id} />}
    </Drawer>
  );
}

function Body({ id }: { id: number }) {
  const { can } = useAuth();
  const { data: o } = useGet<OutageDetail>(`/outages/${id}`);
  const crews = useGet<Crew[]>(o && ["reported", "assessed", "assigned"].includes(o.status) ? "/crews?status=available,staged&kind=line" : null);
  const [crewId, setCrewId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [etr, setEtr] = useState<Date | null>(null);
  const inv = ["/outages", "/events", "/crews"];
  const assign = useAction((cid: number) => api.post(`/outages/${id}/assign`, { crew_id: cid }), { success: "Crew assigned", invalidate: inv });
  const status = useAction((st: string) => api.post(`/outages/${id}/status`, { status: st }), { success: "Ticket updated", invalidate: inv });
  const patch = useAction((b: object) => api.patch(`/outages/${id}`, b), { success: "Saved", invalidate: inv });
  const addNote = useAction(() => api.post(`/outages/${id}/notes`, { text: note }), { success: "Note added", invalidate: [`/outages/${id}`] });
  const setEtrA = useAction(() => api.post(`/outages/${id}/etr`, { etr_at: etr!.toISOString() }), { success: "ETR updated", invalidate: inv });
  if (!o) return <Loader />;
  const manage = can("outages.manage");
  const open = !["restored", "cancelled"].includes(o.status);

  return (
    <Stack gap="md">
      <div>
        <Group gap="xs"><Title order={3}>{o.number}</Title><OutageStatusBadge status={o.status} size="lg" /><PriorityBadge priority={o.priority} /></Group>
        <Text c="dimmed" size="sm">{o.zone} · {o.feeder_id} · {o.device || "device unknown"}</Text>
      </div>
      {o.facility && <Alert color="red" icon={<IconBuildingHospital size={18} />} p="xs">Critical facility: <b>{o.facility}</b></Alert>}

      <SimpleGrid cols={3}>
        <Stat k="Customers" v={fmt(o.customers)} />
        <Stat k={open ? "ETR" : "Restored"} v={open ? (o.etr_at ? dt(o.etr_at) : "—") : dt(o.restored_at)} sub={open && o.etr_at ? (o.etr_override ? "manual" : o.etr_committed ? "committed" : "AI estimate") : undefined} />
        <Stat k="Est. job time" v={`${o.job_hours} h`} sub={`${label(o.cause)} · ${label(o.damage)}`} />
      </SimpleGrid>

      {manage && open && (
        <Stack gap="xs">
          <Divider label="Dispatch" labelPosition="left" />
          <Group align="flex-end" gap="xs">
            <Select style={{ flex: 1 }} label={o.crew ? `Assigned to ${o.crew.code} — reassign` : "Assign a crew"} placeholder="Choose an idle line crew" searchable
              data={(crews.data ?? []).map(c => ({ value: String(c.id), label: `${c.code} · ${c.company} · ${c.size} workers (${c.status})` }))}
              value={crewId} onChange={setCrewId} disabled={!["reported", "assessed", "assigned"].includes(o.status)} nothingFoundMessage="No idle line crews" />
            <Button leftSection={<IconUserCheck size={16} />} disabled={!crewId} loading={assign.isPending} onClick={() => crewId && assign.mutate(Number(crewId))}>Assign</Button>
          </Group>
          <Group gap="xs">
            {o.allowed.includes("in_progress") && <Button variant="light" leftSection={<IconPlayerPlay size={16} />} onClick={() => status.mutate("in_progress")}>Crew on site</Button>}
            {o.allowed.includes("restored") && <Button variant="light" color="teal" leftSection={<IconCheck size={16} />} onClick={() => status.mutate("restored")}>Mark restored</Button>}
            {o.allowed.includes("cancelled") && <Button variant="subtle" color="gray" onClick={() => status.mutate("cancelled")}>Cancel ticket</Button>}
          </Group>
          <Divider label="Assessment" labelPosition="left" />
          <Grid gutter="xs">
            <Grid.Col span={4}><Select label="Cause" data={CAUSES.map(c => ({ value: c, label: label(c) }))} value={o.cause} onChange={v => v && patch.mutate({ cause: v })} /></Grid.Col>
            <Grid.Col span={4}><Select label="Damage" data={DAMAGE.map(c => ({ value: c, label: label(c) }))} value={o.damage} onChange={v => v && patch.mutate({ damage: v })} /></Grid.Col>
            <Grid.Col span={4}><Select label="Priority" data={["critical", "high", "normal"].map(c => ({ value: c, label: label(c) }))} value={o.priority} onChange={v => v && patch.mutate({ priority: v })} /></Grid.Col>
          </Grid>
          <Group align="flex-end" gap="xs">
            <DateTimePicker style={{ flex: 1 }} label="Override ETR" placeholder="Pick date and time" value={etr} onChange={setEtr} minDate={new Date()} valueFormat="ddd MMM D, h:mm A" />
            <Button variant="default" leftSection={<IconClock size={16} />} disabled={!etr} onClick={() => setEtrA.mutate()}>Set ETR</Button>
          </Group>
        </Stack>
      )}

      <Divider label="Activity" labelPosition="left" />
      <Group align="flex-end" gap="xs">
        <Textarea style={{ flex: 1 }} placeholder="Add a note for the field or dispatch…" autosize minRows={1} value={note} onChange={e => setNote(e.currentTarget.value)} />
        <Button variant="default" disabled={!note.trim()} onClick={() => { addNote.mutate(); setNote(""); }}>Add note</Button>
      </Group>
      <Timeline bulletSize={18} lineWidth={2}>
        {o.history.map(h => (
          <Timeline.Item key={h.id} bullet={h.kind === "created" ? <IconAlertTriangle size={11} /> : undefined}
            title={<Text size="sm">{h.text}</Text>}>
            <Text size="xs" c="dimmed">{h.user} · {dt(h.at)} ({ago(h.at)})</Text>
          </Timeline.Item>
        ))}
      </Timeline>
      <Group gap="xs"><Badge variant="outline" color="gray">Source: {o.source}</Badge><Badge variant="outline" color="gray">Reported {ago(o.reported_at)}</Badge></Group>
    </Stack>
  );
}

function Stat({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{k}</Text>
      <Text fw={600} size="sm">{v}</Text>
      {sub && <Text size="xs" c="dimmed">{sub}</Text>}
    </div>
  );
}
