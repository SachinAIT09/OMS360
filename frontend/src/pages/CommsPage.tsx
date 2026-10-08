import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ActionIcon, Badge, Button, Card, Grid, Group, Menu, Modal, Paper, Select, SimpleGrid, Stack, Switch, Table, Tabs, Text, Textarea, TextInput, Tooltip,
} from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { modals } from "@mantine/modals";
import {
  IconBrandFacebook, IconBrandX, IconCheck, IconDots, IconMail, IconMessage, IconPencil, IconPhone, IconPlus, IconSend, IconSparkles, IconWorld, IconX,
} from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction, useGet, useReference } from "../api/hooks";
import type { Audience, Message, Rule } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useCurrentEvent } from "../auth/EventContext";
import { MessageStatusBadge } from "../components/badges";
import { Empty, Loading, PageHeader, Stat } from "../components/common";
import { ago, dt, fmt } from "../lib/format";

const CH_ICON: Record<string, JSX.Element> = {
  x: <IconBrandX size={16} />, facebook: <IconBrandFacebook size={16} />, sms: <IconMessage size={16} />, email: <IconMail size={16} />, ivr: <IconPhone size={16} />, website: <IconWorld size={16} />,
};
const TABS = [["pending", "Pending approval"], ["draft", "Drafts"], ["scheduled", "Scheduled"], ["sent", "Sent"], ["rejected", "Rejected"]] as const;

export default function CommsPage() {
  const { event } = useCurrentEvent();
  const { can, user } = useAuth();
  const ref = useReference();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "pending";
  const all = useGet<Message[]>(event ? `/messages?event_id=${event.id}` : null);
  const stats = useGet<{ by_status: Record<string, { count: number; recipients: number }>; automated_sent: number }>(event ? `/messages/stats?event_id=${event.id}` : null);
  const rules = useGet<Rule[]>("/notification-rules");
  const audiences = useGet<Audience[]>(event ? `/comms/audiences?event_id=${event.id}` : null);
  const [compose, setCompose] = useState<Message | "new" | null>(null);
  const approve = useAction((id: number) => api.post(`/messages/${id}/approve`), { success: "Approved and sent" });
  const submit = useAction((id: number) => api.post(`/messages/${id}/submit`), { success: "Submitted for approval" });
  const reject = useAction(({ id, reason }: { id: number; reason: string }) => api.post(`/messages/${id}/reject`, { reason }), { success: "Sent back to the author" });
  const remove = useAction((id: number) => api.del(`/messages/${id}`), { success: "Draft deleted" });
  const rule = useAction(({ id, on }: { id: number; on: boolean }) => api.patch(`/notification-rules/${id}`, { enabled: on }), { success: "Rule updated" });

  if (!event) return <Empty title="Select a storm event" />;
  const list = (all.data ?? []).filter(m => m.status === tab);
  const count = (s: string) => (all.data ?? []).filter(m => m.status === s).length;
  const audName = (id: string) => audiences.data?.find(a => a.id === id)?.name ?? id;
  const sent = stats.data?.by_status.sent;

  const askReject = (m: Message) => {
    let reason = "";
    modals.openConfirmModal({
      title: "Send back for changes", labels: { confirm: "Send back", cancel: "Cancel" }, confirmProps: { color: "red" },
      children: <Textarea label="What needs to change?" autosize minRows={2} onChange={e => { reason = e.currentTarget.value; }} />,
      onConfirm: () => reject.mutate({ id: m.id, reason }),
    });
  };

  return (
    <>
      <PageHeader title="Communications" description="Customer messages for this storm. Everything public goes through approval."
        actions={can("messages.create") && <Button leftSection={<IconPlus size={16} />} onClick={() => setCompose("new")}>New message</Button>} />
      <SimpleGrid cols={{ base: 2, md: 4 }} mb="lg">
        <Stat label="Waiting for approval" value={count("pending")} color={count("pending") ? "yellow" : undefined} onClick={() => setParams({ tab: "pending" })} />
        <Stat label="Messages sent" value={fmt(sent?.count ?? 0)} color="teal" hint={`${fmt(sent?.recipients ?? 0)} recipients`} />
        <Stat label="Automated notifications" value={fmt(stats.data?.automated_sent ?? 0)} hint="outage / restoration texts from rules" />
        <Stat label="Scheduled" value={count("scheduled")} />
      </SimpleGrid>
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, xl: 8 }}>
          <Card padding={0}>
            <Tabs value={tab} onChange={v => setParams({ tab: v! })}>
              <Tabs.List px="sm" pt="xs">
                {TABS.map(([k, l]) => <Tabs.Tab key={k} value={k} rightSection={count(k) ? <Badge size="xs" variant="light" color={k === "pending" ? "yellow" : "gray"}>{count(k)}</Badge> : undefined}>{l}</Tabs.Tab>)}
              </Tabs.List>
            </Tabs>
            {!all.data ? <Loading /> : !list.length ? <Empty title={`No ${TABS.find(t => t[0] === tab)?.[1].toLowerCase()} messages`} /> : (
              <Stack gap={0}>
                {list.map(m => (
                  <Paper key={m.id} p="md" radius={0} style={{ borderBottom: "1px solid var(--mantine-color-default-border)" }}>
                    <Group justify="space-between" wrap="nowrap" align="flex-start">
                      <Group gap="xs" wrap="nowrap">
                        <ActionIcon variant="light" size="lg" radius="md">{CH_ICON[m.channel]}</ActionIcon>
                        <div>
                          <Group gap={6}><Text fw={600} size="sm">{ref.data?.channels[m.channel] ?? m.channel}</Text><Text size="sm" c="dimmed">→ {audName(m.audience)}</Text>
                            <MessageStatusBadge status={m.status} size="sm" />{m.ai_generated && <Badge size="sm" color="ai" leftSection={<IconSparkles size={10} />}>AI draft</Badge>}</Group>
                          <Text size="xs" c="dimmed">{m.created_by} · {ago(m.created_at)}{m.approved_by && ` · approved by ${m.approved_by}`}{m.sent_at && ` · sent ${dt(m.sent_at)}`}
                            {m.scheduled_for && m.status === "scheduled" && ` · goes out ${dt(m.scheduled_for)}`} · {fmt(m.recipients)} recipients</Text>
                        </div>
                      </Group>
                      <Group gap={6} wrap="nowrap">
                        {m.status === "pending" && can("messages.approve") && <>
                          <Button size="compact-sm" variant="default" color="red" leftSection={<IconX size={14} />} onClick={() => askReject(m)}>Send back</Button>
                          <Button size="compact-sm" color="teal" leftSection={<IconCheck size={14} />} loading={approve.isPending} onClick={() => approve.mutate(m.id)}>{m.scheduled_for ? "Approve & schedule" : "Approve & send"}</Button>
                        </>}
                        {["draft", "rejected"].includes(m.status) && can("messages.create") && <Button size="compact-sm" leftSection={<IconSend size={14} />} onClick={() => submit.mutate(m.id)}>Submit</Button>}
                        {["draft", "pending", "rejected"].includes(m.status) && can("messages.create") && (
                          <Menu position="bottom-end"><Menu.Target><ActionIcon variant="subtle" color="gray"><IconDots size={16} /></ActionIcon></Menu.Target>
                            <Menu.Dropdown>
                              <Menu.Item leftSection={<IconPencil size={14} />} onClick={() => setCompose(m)}>Edit</Menu.Item>
                              <Menu.Item color="red" onClick={() => remove.mutate(m.id)}>Delete</Menu.Item>
                            </Menu.Dropdown></Menu>)}
                      </Group>
                    </Group>
                    {m.subject && <Text size="sm" fw={600} mt="sm">{m.subject}</Text>}
                    <Text size="sm" mt={m.subject ? 2 : "sm"} className="pre-wrap" lineClamp={6}>{m.body}</Text>
                    {m.status === "rejected" && m.reject_reason && <Text size="xs" c="red" mt={6}>Sent back: {m.reject_reason}</Text>}
                  </Paper>))}
              </Stack>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, xl: 4 }}>
          <Stack>
            <Card>
              <Text fw={600} mb="xs">Automated notification rules</Text>
              <Stack gap="sm">
                {(rules.data ?? []).map(r => (
                  <Group key={r.id} wrap="nowrap" justify="space-between" align="flex-start">
                    <div><Text size="sm">{r.name}</Text><Text size="xs" c="dimmed">{fmt(r.sent_count)} sent</Text></div>
                    <Switch checked={r.enabled} disabled={!can("messages.approve")} onChange={e => rule.mutate({ id: r.id, on: e.currentTarget.checked })} />
                  </Group>))}
              </Stack>
            </Card>
            <Card padding={0}>
              <Text fw={600} p="md" pb={0}>Audiences</Text>
              <Table mt="xs"><Table.Tbody>{(audiences.data ?? []).slice(0, 5).map(a => (
                <Table.Tr key={a.id}><Table.Td>{a.name}</Table.Td><Table.Td ta="right" className="tabular">{fmt(a.count)}</Table.Td></Table.Tr>))}</Table.Tbody></Table>
              <Text size="xs" c="dimmed" p="sm">Zone, region and circuit audiences are also available when composing.</Text>
            </Card>
          </Stack>
        </Grid.Col>
      </Grid>
      {compose && <Compose eventId={event.id} message={compose === "new" ? null : compose} audiences={audiences.data ?? []} onClose={() => setCompose(null)} author={user?.name ?? ""} />}
    </>
  );
}

function Compose({ eventId, message, audiences, onClose }: { eventId: number; message: Message | null; audiences: Audience[]; onClose: () => void; author: string }) {
  const ref = useReference();
  const [channel, setChannel] = useState(message?.channel ?? "sms");
  const [purpose, setPurpose] = useState<string | null>(null);
  const [audience, setAudience] = useState(message?.audience ?? "all");
  const [subject, setSubject] = useState(message?.subject ?? "");
  const [body, setBody] = useState(message?.body ?? "");
  const [schedule, setSchedule] = useState<Date | null>(message?.scheduled_for ? new Date(message.scheduled_for) : null);
  const [ai, setAi] = useState(message?.ai_generated ?? false);
  const draft = useAction(() => api.post<{ subject: string; body: string; purpose: string }>("/messages/ai-draft", { event_id: eventId, channel, purpose }),
    { invalidate: [] });
  const save = useAction((submit: boolean) => message
      ? api.patch(`/messages/${message.id}`, { subject, body, audience, scheduled_for: schedule?.toISOString() ?? null }).then(r => (submit ? api.post(`/messages/${message.id}/submit`) : r))
      : api.post("/messages", { event_id: eventId, channel, audience, subject, body, ai_generated: ai, submit, scheduled_for: schedule?.toISOString() ?? null }),
    { success: "Message saved" });
  const limit = channel === "x" ? 280 : channel === "sms" ? 320 : 5000;
  const aud = audiences.find(a => a.id === audience);

  return (
    <Modal opened onClose={onClose} title={message ? "Edit message" : "New message"} size="xl">
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="sm">
            <Group grow>
              <Select label="Channel" disabled={!!message} value={channel} onChange={v => v && setChannel(v)}
                data={Object.entries(ref.data?.channels ?? {}).map(([value, label]) => ({ value, label }))} />
              <Select label="Audience" searchable value={audience} onChange={v => v && setAudience(v)}
                data={audiences.map(a => ({ value: a.id, label: `${a.name} (${fmt(a.count)})` }))} />
            </Group>
            <Group align="flex-end" gap="xs">
              <Select style={{ flex: 1 }} label="Purpose" placeholder="Based on event status" clearable value={purpose} onChange={setPurpose}
                data={Object.entries(ref.data?.purposes ?? {}).map(([value, label]) => ({ value, label }))} />
              <Button variant="light" color="ai" leftSection={<IconSparkles size={16} />} loading={draft.isPending}
                onClick={async () => { const d = await draft.mutateAsync(); setBody(d.body); setSubject(d.subject); setAi(true); }}>Draft with AI</Button>
            </Group>
            {channel === "email" && <TextInput label="Subject" value={subject} onChange={e => setSubject(e.currentTarget.value)} />}
            <Textarea label="Message" autosize minRows={6} maxRows={14} value={body} onChange={e => setBody(e.currentTarget.value)}
              description={`${body.length} / ${limit} characters${channel === "sms" ? ` · ${Math.ceil(body.length / 160) || 1} SMS segment(s)` : ""}`} error={body.length > limit ? "Too long for this channel" : undefined} />
            <DateTimePicker label="Schedule" placeholder="Send as soon as approved" clearable value={schedule} onChange={setSchedule} minDate={new Date()} valueFormat="ddd MMM D, h:mm A" />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Text size="sm" fw={600} mb={6}>Preview</Text>
          <Paper withBorder p="md" radius="lg" bg={channel === "sms" ? "var(--mantine-color-default-hover)" : undefined}>
            <Group gap={6} mb="xs">{CH_ICON[channel]}<Text size="xs" c="dimmed">{ref.data?.channels[channel]} · Bayview Power & Water</Text></Group>
            {subject && <Text fw={600} size="sm">{subject}</Text>}
            <Text size="sm" className="pre-wrap">{body || <Text span c="dimmed">Your message will appear here.</Text>}</Text>
          </Paper>
          <Text size="xs" c="dimmed" mt="sm">Estimated reach: <b>{fmt(aud ? (channel === "x" ? 48200 : channel === "facebook" ? 61500 : channel === "sms" ? aud.count * 0.71 : channel === "email" ? aud.count * 0.54 : 0) : 0)}</b>
            {["ivr", "website"].includes(channel) && " (on demand)"}</Text>
          <Tooltip label="Public messages always need approval from an executive, operations manager or communications lead.">
            <Badge mt="sm" variant="outline" color="gray">Approval required</Badge>
          </Tooltip>
        </Grid.Col>
      </Grid>
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose}>Cancel</Button>
        <Button variant="default" disabled={!body.trim() || body.length > limit} loading={save.isPending} onClick={async () => { await save.mutateAsync(false); onClose(); }}>Save draft</Button>
        <Button leftSection={<IconSend size={16} />} disabled={!body.trim() || body.length > limit} loading={save.isPending} onClick={async () => { await save.mutateAsync(true); onClose(); }}>Submit for approval</Button>
      </Group>
    </Modal>
  );
}
