import { useEffect, useRef, useState, type ReactNode } from "react";
import { ActionIcon, Badge, Box, Button, CloseButton, CopyButton, Group, Loader, Menu, Paper, ScrollArea, Stack, Switch, Text, Textarea, TextInput, ThemeIcon, Tooltip, UnstyledButton } from "@mantine/core";
import dayjs from "dayjs";
import { useLocalStorage } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import { IconArrowUp, IconBolt, IconBookmark, IconBookmarkFilled, IconCheck, IconChecklist, IconChevronDown, IconCopy, IconEdit, IconFileText, IconHistory, IconMicrophone,
  IconPlus, IconRobot, IconSearch, IconSparkles, IconTrash, IconUsersGroup } from "@tabler/icons-react";
import { api } from "../api/client";
import { invalidate, useGet } from "../api/hooks";
import type { JarvisConversation, JarvisMessage, JarvisSaved } from "../api/types";
import { useCurrentEvent } from "../auth/EventContext";
import { AnswerBody, speak, useAssistantAction, useVoiceInput } from "../components/JarvisChat";
import { ago } from "../lib/format";

const STARTERS = [
  { label: "Situation briefing", prompt: "Give me a situation briefing", icon: IconFileText, color: "brand" },
  { label: "Do I need more crews?", prompt: "Do I need more people?", icon: IconUsersGroup, color: "teal" },
  { label: "Hardest-hit areas", prompt: "Which areas will be hit hardest?", icon: IconBolt, color: "orange" },
  { label: "Waiting for approval", prompt: "What's waiting for approval?", icon: IconChecklist, color: "ai" },
];
const MORE_PROMPTS = ["When will Riverview be restored?", "What if it becomes a Cat 4?", "What if it brings 10 inches of rain?", "What are the ETRs in the South Shore region?", "How many tickets are unassigned?", "Are the hospitals at risk?",
  "What about the water system?", "Draft a post for Brandon customers", "How much will this storm cost?", "Where is the storm now?"];

/** `null` = the user's most recent conversation, 0 = a fresh one, otherwise a specific conversation. */
type ConvSel = number | null;

export default function JarvisPage() {
  const { event } = useCurrentEvent();
  const qc = useQueryClient();
  const act = useAssistantAction();
  const [voice, setVoice] = useLocalStorage({ key: "oms360_voice", defaultValue: true });
  const [talking, setTalking] = useState(false);
  const [conv, setConv] = useState<ConvSel>(null);
  const [panel, setPanel] = useState<"history" | "saved" | null>(null);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const qs = new URLSearchParams();
  if (event) qs.set("event_id", String(event.id));
  if (conv !== null) qs.set("conversation_id", String(conv));
  const { data, isLoading } = useGet<JarvisMessage[]>(`/jarvis/messages?${qs}`);
  const thread = [...(data ?? []).slice(1), ...(pending ? [{ role: "user" as const, text: pending }] : [])];
  const empty = !isLoading && thread.length === 0;

  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [thread.length, pending]);

  const ask = async (q: string) => {
    q = q.trim();
    if (!q || pending) return;
    setInput(""); setPending(q);
    try {
      const r = await api.post<JarvisMessage>("/jarvis/ask", { question: q, event_id: event?.id, conversation_id: conv ?? undefined });
      if (r.conversation_id) setConv(r.conversation_id);
      if (voice) speak(r.say || r.text.replace(/\*\*/g, ""), () => setTalking(true), () => setTalking(false));
    } catch (e) {
      notifications.show({ color: "red", message: `AI Assistant is unavailable: ${(e as Error).message}` });
      setInput(q);
    } finally {
      setPending(null);
      invalidate(qc, ["/jarvis"]);
    }
  };
  const { listening, listen } = useVoiceInput(setInput, ask);

  const newChat = () => { setConv(0); setInput(""); };
  const toggleSaved = async (m: JarvisMessage) => {
    try {
      await api.put(`/jarvis/messages/${m.id}/saved`, { saved: !m.saved });
      notifications.show({ color: "teal", message: m.saved ? "Removed from saved answers" : "Saved — find it under Saved answers" });
    } catch (e) { notifications.show({ color: "red", message: (e as Error).message }); }
    invalidate(qc, ["/jarvis"]);
  };

  return (
    <Box className="assistant-shell">
      <Group justify="space-between" mb="md" wrap="nowrap">
        <Group gap="sm" wrap="nowrap">
          <ThemeIcon size={44} radius="md" variant="gradient" gradient={{ from: "brand.5", to: "ai.5", deg: 135 }}><IconRobot size={24} /></ThemeIcon>
          <div>
            <Text fw={700} size="xl" lh={1.2}>AI Assistant</Text>
            <Text size="sm" c="dimmed">Ask about the storm, crews, outages, restoration times and customers.</Text>
          </div>
        </Group>
        <Group gap="md" wrap="nowrap" visibleFrom="sm">
          {event && <Badge variant="light" color="ai" size="lg">{event.name}</Badge>}
          <Switch label="Voice reply" checked={voice} onChange={e => setVoice(e.currentTarget.checked)} />
        </Group>
      </Group>

      <Group align="stretch" gap="md" wrap="nowrap" style={{ flex: 1, minHeight: 0 }}>
        <Stack gap="md" style={{ flex: 1, minWidth: 0 }}>
          <ScrollArea viewportRef={scroller} style={{ flex: 1 }} type="auto" offsetScrollbars>
            <Box className="assistant-column">
              {isLoading ? <Group justify="center" mt="xl"><Loader color="ai" type="dots" /></Group>
                : empty ? <Hero talking={talking} onAsk={ask} />
                : <Stack gap="lg" py="md">
                    {thread.map((m, i) => m.role === "user"
                      ? <Paper key={m.id ?? `p${i}`} className="assistant-user" px="md" py="xs" radius="xl"><Text size="sm">{m.text}</Text></Paper>
                      : <Group key={m.id ?? `p${i}`} align="flex-start" gap="sm" wrap="nowrap">
                          <AssistantAvatar />
                          <Box style={{ flex: 1, minWidth: 0 }}>
                            <AnswerBody m={m} onAction={act} />
                            {!!m.id && <Group gap={2} mt={6} className="assistant-tools">
                              <CopyButton value={[m.text, ...(m.bullets ?? []).map(b => `• ${b}`), m.quote ?? ""].filter(Boolean).join("\n").replace(/\*\*/g, "")}>
                                {({ copied, copy }) => <Tooltip label={copied ? "Copied" : "Copy"}><ActionIcon variant="subtle" color="gray" size="sm" onClick={copy} aria-label="Copy answer">
                                  {copied ? <IconCheck size={15} /> : <IconCopy size={15} />}</ActionIcon></Tooltip>}
                              </CopyButton>
                              <Tooltip label={m.saved ? "Remove from saved" : "Save answer"}>
                                <ActionIcon variant="subtle" color={m.saved ? "ai" : "gray"} size="sm" onClick={() => toggleSaved(m)} aria-label={m.saved ? "Remove from saved" : "Save answer"}>
                                  {m.saved ? <IconBookmarkFilled size={15} /> : <IconBookmark size={15} />}</ActionIcon>
                              </Tooltip>
                            </Group>}
                          </Box>
                        </Group>)}
                    {pending && <Group gap="sm" wrap="nowrap"><AssistantAvatar /><Loader color="ai" type="dots" size="sm" /></Group>}
                  </Stack>}
            </Box>
          </ScrollArea>

          <Box className="assistant-column" style={{ flex: "none" }}>
            <div className="assistant-composer">
              <Textarea variant="unstyled" autosize minRows={1} maxRows={5} placeholder="Type your message" value={input} style={{ flex: 1 }}
                onChange={e => setInput(e.currentTarget.value)} aria-label="Message the AI Assistant"
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); } }} />
              <Tooltip label={listening ? "Listening…" : "Talk (Chrome / Edge)"}>
                <ActionIcon size={40} radius="xl" color={listening ? "red" : "brand"} className={listening ? "mic-rec" : undefined} onClick={listen} aria-label="Voice input">
                  <IconMicrophone size={19} /></ActionIcon>
              </Tooltip>
              <ActionIcon size={40} radius="xl" color="brand" onClick={() => ask(input)} disabled={!input.trim() || !!pending} aria-label="Send"><IconArrowUp size={19} /></ActionIcon>
            </div>
          </Box>
        </Stack>

        <Paper className={`assistant-rail${panel ? " open" : ""}`} withBorder radius="lg" onKeyDown={e => e.key === "Escape" && setPanel(null)}>
          <div className="assistant-rail-panel" aria-hidden={!panel}>
            {panel === "history" && <HistoryPanel current={conv} onOpen={setConv} onDeleted={id => { if (id === conv) setConv(null); }} onViewSaved={() => setPanel("saved")} />}
            {panel === "saved" && <SavedPanel onOpen={setConv} onToggle={toggleSaved} />}
          </div>
          <Stack gap={6} align="center" p={8} className="assistant-rail-icons">
            <RailButton label="New chat" onClick={newChat}><IconEdit size={20} /></RailButton>
            <RailButton label={panel === "history" ? "Hide history" : "History"} active={panel === "history"} onClick={() => setPanel(p => p === "history" ? null : "history")}><IconHistory size={20} /></RailButton>
            <RailButton label={panel === "saved" ? "Hide saved answers" : "Saved answers"} active={panel === "saved"} onClick={() => setPanel(p => p === "saved" ? null : "saved")}><IconBookmark size={20} /></RailButton>
          </Stack>
        </Paper>
      </Group>
    </Box>
  );
}

function Hero({ talking, onAsk }: { talking: boolean; onAsk: (q: string) => void }) {
  return (
    <Stack align="center" gap="md" className="assistant-hero">
      <div className={`assistant-mark${talking ? " talk" : ""}`}><IconSparkles size={34} stroke={1.6} /></div>
      <Text fw={700} fz={26} ta="center" mt="xs">PowerConnect AI Assistant</Text>
      <Text c="dimmed" ta="center">What's on your mind? How may I assist you today?</Text>
      <Group justify="center" gap="sm" mt="xs">
        {STARTERS.map(s => (
          <Button key={s.label} variant="default" radius="xl" size="sm" className="assistant-chip" leftSection={<s.icon size={15} color={`var(--mantine-color-${s.color}-5)`} />}
            onClick={() => onAsk(s.prompt)}>{s.label}</Button>))}
        <Menu position="bottom" width={280} shadow="md">
          <Menu.Target><Button variant="default" radius="xl" size="sm" className="assistant-chip" leftSection={<IconPlus size={15} />}>More Question</Button></Menu.Target>
          <Menu.Dropdown>{MORE_PROMPTS.map(p => <Menu.Item key={p} onClick={() => onAsk(p)}>{p}</Menu.Item>)}</Menu.Dropdown>
        </Menu>
      </Group>
    </Stack>
  );
}

function AssistantAvatar() {
  return <div className="assistant-avatar"><IconSparkles size={16} stroke={1.8} /></div>;
}

function RailButton({ label, active, onClick, children }: { label: string; active?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <Tooltip label={label} position="left">
      <ActionIcon size={42} radius="xl" variant={active ? "light" : "subtle"} color={active ? "brand" : "gray"} className={active ? "assistant-rail-active" : undefined}
        onClick={onClick} aria-label={label} aria-pressed={active}>{children}</ActionIcon>
    </Tooltip>
  );
}

/** Today / Yesterday / Previous 7 days / Older, newest first. */
function byDay(rows: JarvisConversation[]) {
  const today = dayjs().startOf("day");
  const bucket = (iso: string) => {
    const d = dayjs(iso);
    return d.isAfter(today) ? "Today" : d.isAfter(today.subtract(1, "day")) ? "Yesterday" : d.isAfter(today.subtract(7, "day")) ? "Previous 7 days" : "Older";
  };
  const groups = new Map<string, JarvisConversation[]>();
  for (const r of rows) groups.set(bucket(r.updated_at), [...(groups.get(bucket(r.updated_at)) ?? []), r]);
  return [...groups.entries()];
}

function PanelHeader({ title, children }: { title: string; children?: ReactNode }) {
  return <Group justify="space-between" wrap="nowrap" px="md" pt="md" pb="xs"><Text fw={700}>{title}</Text>{children}</Group>;
}

function HistoryPanel({ current, onOpen, onDeleted, onViewSaved }: { current: ConvSel; onOpen: (id: number) => void; onDeleted: (id: number) => void; onViewSaved: () => void }) {
  const qc = useQueryClient();
  const { data } = useGet<JarvisConversation[]>("/jarvis/conversations");
  const { data: saved } = useGet<JarvisSaved[]>("/jarvis/saved");
  const [searching, setSearching] = useState(false);
  const [q, setQ] = useState("");
  const [savedOpen, setSavedOpen] = useState(true);
  const latest = data?.[0]?.id;
  const needle = q.trim().toLowerCase();
  const rows = (data ?? []).filter(c => !needle || c.title.toLowerCase().includes(needle));
  const savedRows = (saved ?? []).filter(m => !needle || (m.question ?? m.text).toLowerCase().includes(needle));

  const remove = async (id: number) => {
    try { await api.del(`/jarvis/conversations/${id}`); onDeleted(id); }
    catch (e) { notifications.show({ color: "red", message: (e as Error).message }); }
    invalidate(qc, ["/jarvis"]);
  };

  return (
    <div className="assistant-panel">
      <PanelHeader title="Recent History">
        <Tooltip label="Search history"><ActionIcon variant={searching ? "light" : "subtle"} color="gray" onClick={() => { setSearching(s => !s); setQ(""); }} aria-label="Search history">
          <IconSearch size={18} /></ActionIcon></Tooltip>
      </PanelHeader>
      {searching && <TextInput mx="md" mb="xs" size="xs" autoFocus placeholder="Search conversations" value={q} onChange={e => setQ(e.currentTarget.value)}
        rightSection={q ? <CloseButton size="sm" onClick={() => setQ("")} aria-label="Clear search" /> : null} />}
      <ScrollArea style={{ flex: 1 }} type="auto" px="md" pb="md">
        {!!savedRows.length && <>
          <UnstyledButton className="assistant-section" onClick={() => setSavedOpen(o => !o)} aria-expanded={savedOpen}>
            <IconChevronDown size={15} className={savedOpen ? undefined : "assistant-chevron-closed"} /><Text size="sm" fw={600}>Saved answers</Text>
          </UnstyledButton>
          {savedOpen && <Stack gap={6} mb={4}>
            {savedRows.slice(0, 5).map(m => (
              <UnstyledButton key={m.id} className="assistant-item" onClick={() => onOpen(m.conversation_id)}>
                <IconBookmarkFilled size={13} color="var(--mantine-color-ai-4)" style={{ flex: "none" }} /><Text size="sm" truncate>{m.question ?? m.text.replace(/\*\*/g, "")}</Text>
              </UnstyledButton>))}
            {savedRows.length > 5 && <Button variant="subtle" size="compact-xs" ml="auto" onClick={onViewSaved}>View all {savedRows.length}</Button>}
          </Stack>}
        </>}
        {!data ? <Group justify="center" mt="md"><Loader color="ai" type="dots" /></Group>
          : !rows.length ? <Text size="sm" c="dimmed" ta="center" mt="md">{needle ? "No conversations match." : "No conversations yet. Ask a question to start one."}</Text>
          : byDay(rows).map(([day, list]) => (
            <Box key={day}>
              <Text size="sm" fw={600} mt="md" mb={6}>{day}</Text>
              <Stack gap={6}>{list.map(c => {
                const active = current === c.id || (current === null && c.id === latest);
                return (
                  <div key={c.id} className={`assistant-item${active ? " active" : ""}`}>
                    <UnstyledButton style={{ flex: 1, minWidth: 0 }} onClick={() => onOpen(c.id)} title={`${c.title} · ${ago(c.updated_at)}`}>
                      <Text size="sm" fw={500} truncate>{c.title}</Text>
                    </UnstyledButton>
                    <ActionIcon className="assistant-item-delete" variant="subtle" color="gray" size="sm" onClick={() => remove(c.id)} aria-label={`Delete ${c.title}`}><IconTrash size={14} /></ActionIcon>
                  </div>
                );
              })}</Stack>
            </Box>))}
      </ScrollArea>
    </div>
  );
}

function SavedPanel({ onOpen, onToggle }: { onOpen: (conversationId: number) => void; onToggle: (m: JarvisMessage) => void }) {
  const { data } = useGet<JarvisSaved[]>("/jarvis/saved");
  return (
    <div className="assistant-panel">
      <PanelHeader title="Saved answers">{data && <Badge variant="light" color="ai">{data.length}</Badge>}</PanelHeader>
      <ScrollArea style={{ flex: 1 }} type="auto" px="md" pb="md">
        {!data ? <Group justify="center" mt="md"><Loader color="ai" type="dots" /></Group>
          : !data.length ? <Text size="sm" c="dimmed" ta="center" mt="md">Nothing saved yet. Use the bookmark under any answer to keep it here.</Text>
          : <Stack gap={8}>{data.map(m => (
              <div key={m.id} className="assistant-item assistant-saved">
                <UnstyledButton style={{ flex: 1, minWidth: 0 }} onClick={() => onOpen(m.conversation_id)}>
                  {m.question && <Text size="sm" fw={600} truncate>{m.question}</Text>}
                  <Text size="xs" c="dimmed" lineClamp={3}>{m.text.replace(/\*\*/g, "")}</Text>
                  <Text size="xs" c="dimmed" mt={4}>{ago(m.created_at)}</Text>
                </UnstyledButton>
                <Tooltip label="Remove from saved"><ActionIcon variant="subtle" color="ai" size="sm" onClick={() => onToggle(m)} aria-label="Remove from saved"><IconBookmarkFilled size={15} /></ActionIcon></Tooltip>
              </div>))}
            </Stack>}
      </ScrollArea>
    </div>
  );
}
