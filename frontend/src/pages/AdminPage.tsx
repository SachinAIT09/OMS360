import { useState } from "react";
import { Navigate } from "react-router-dom";
import {
  Alert, Badge, Button, Card, Grid, Group, Modal, NumberInput, PasswordInput, SegmentedControl, Select, Stack, Switch, Table, Tabs, Text, TextInput,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { IconCloud, IconHistory, IconMapPin, IconPlugConnected, IconRoute, IconSearch, IconUserPlus, IconUsers } from "@tabler/icons-react";
import { api, qs } from "../api/client";
import { useAction, useGet, useReference } from "../api/hooks";
import type { Audit, User, Weather } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Loading, PageHeader } from "../components/common";
import { NetworkAdmin } from "../components/NetworkAdmin";
import { ago, dt, fmt } from "../lib/format";

const ROLES = [{ value: "executive", label: "Executive" }, { value: "ops_manager", label: "Operations Manager" }, { value: "dispatcher", label: "Dispatcher" },
  { value: "comms", label: "Communications Lead" }, { value: "admin", label: "Administrator" }];

export default function AdminPage() {
  const { can } = useAuth();
  if (!can("admin")) return <Navigate to="/" replace />;
  return (
    <>
      <PageHeader title="Administration" description="Users, network data, integrations and the audit trail." />
      <Tabs defaultValue="users" keepMounted={false}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="users" leftSection={<IconUsers size={16} />}>Users</Tabs.Tab>
          <Tabs.Tab value="zones" leftSection={<IconMapPin size={16} />}>Zones</Tabs.Tab>
          <Tabs.Tab value="network" leftSection={<IconRoute size={16} />}>Network</Tabs.Tab>
          <Tabs.Tab value="integrations" leftSection={<IconPlugConnected size={16} />}>Integrations</Tabs.Tab>
          <Tabs.Tab value="audit" leftSection={<IconHistory size={16} />}>Audit log</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="users"><Users /></Tabs.Panel>
        <Tabs.Panel value="zones"><Zones /></Tabs.Panel>
        <Tabs.Panel value="network"><NetworkAdmin /></Tabs.Panel>
        <Tabs.Panel value="integrations"><Integrations /></Tabs.Panel>
        <Tabs.Panel value="audit"><AuditLog /></Tabs.Panel>
      </Tabs>
    </>
  );
}

function Users() {
  const { user: me } = useAuth();
  const { data } = useGet<User[]>("/admin/users");
  const [open, ctl] = useDisclosure(false);
  const update = useAction(({ id, body }: { id: number; body: object }) => api.patch(`/admin/users/${id}`, body), { success: "User updated" });
  const form = useForm({ initialValues: { name: "", email: "", title: "", role: "dispatcher", password: "" },
    validate: { email: (v: string) => (/\S+@\S+/.test(v) ? null : "Email required"), name: (v: string) => (v.length > 1 ? null : "Name required"), password: (v: string) => (v.length >= 6 ? null : "At least 6 characters") } });
  const create = useAction((v: typeof form.values) => api.post("/admin/users", v), { success: "User invited" });
  if (!data) return <Loading />;
  return (
    <Card padding={0}>
      <Group p="sm" justify="space-between"><Text fw={600}>{data.length} users</Text><Button size="sm" leftSection={<IconUserPlus size={16} />} onClick={ctl.open}>Add user</Button></Group>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Name</Table.Th><Table.Th>Role</Table.Th><Table.Th>Last sign-in</Table.Th><Table.Th>Active</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{data.map(u => (
          <Table.Tr key={u.id}>
            <Table.Td><Text size="sm" fw={500}>{u.name}</Text><Text size="xs" c="dimmed">{u.email} · {u.title}</Text></Table.Td>
            <Table.Td><Select size="xs" w={190} data={ROLES} value={u.role} disabled={u.id === me?.id} onChange={v => v && update.mutate({ id: u.id, body: { role: v } })} /></Table.Td>
            <Table.Td>{u.last_login_at ? ago(u.last_login_at) : "Never"}</Table.Td>
            <Table.Td><Switch checked={u.active} disabled={u.id === me?.id} onChange={e => update.mutate({ id: u.id, body: { active: e.currentTarget.checked } })} /></Table.Td>
          </Table.Tr>))}
        </Table.Tbody>
      </Table>
      <Modal opened={open} onClose={ctl.close} title="Add user">
        <form onSubmit={form.onSubmit(async v => { await create.mutateAsync(v); ctl.close(); form.reset(); })}>
          <Stack>
            <TextInput label="Full name" {...form.getInputProps("name")} />
            <TextInput label="Work email" {...form.getInputProps("email")} />
            <TextInput label="Job title" {...form.getInputProps("title")} />
            <Select label="Role" data={ROLES} {...form.getInputProps("role")} />
            <PasswordInput label="Temporary password" {...form.getInputProps("password")} />
            <Group justify="flex-end"><Button variant="default" onClick={ctl.close}>Cancel</Button><Button type="submit" loading={create.isPending}>Add user</Button></Group>
          </Stack>
        </form>
      </Modal>
    </Card>
  );
}

function Zones() {
  const ref = useReference();
  const save = useAction(({ id, body }: { id: string; body: object }) => api.patch(`/admin/zones/${id}`, body), { success: "Zone updated", invalidate: ["/reference", "/events"] });
  const [edit, setEdit] = useState<Record<string, { customers: number; vulnerability: number }>>({});
  if (!ref.data) return <Loading />;
  return (
    <Card padding={0}>
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Zone</Table.Th><Table.Th>Flags</Table.Th><Table.Th>Electric customers</Table.Th><Table.Th>Vulnerability</Table.Th><Table.Th ta="right">Water customers</Table.Th><Table.Th /></Table.Tr></Table.Thead>
        <Table.Tbody>{ref.data.zones.map(z => {
          const e = edit[z.id] ?? { customers: z.customers, vulnerability: z.vulnerability };
          const dirty = e.customers !== z.customers || e.vulnerability !== z.vulnerability;
          return (
            <Table.Tr key={z.id}>
              <Table.Td><Text size="sm" fw={500}>{z.name}</Text><Text size="xs" c="dimmed">{z.code}</Text></Table.Td>
              <Table.Td><Group gap={4}>{z.coastal && <Badge size="xs" variant="outline">coastal</Badge>}{z.critical && <Badge size="xs" color="red" variant="outline">hospital</Badge>}{z.medical && <Badge size="xs" color="ai" variant="outline">medical</Badge>}</Group></Table.Td>
              <Table.Td><NumberInput size="xs" w={130} thousandSeparator value={e.customers} onChange={v => setEdit(s => ({ ...s, [z.id]: { ...e, customers: Number(v) } }))} /></Table.Td>
              <Table.Td><NumberInput size="xs" w={100} min={0.1} max={1} step={0.05} decimalScale={2} value={e.vulnerability} onChange={v => setEdit(s => ({ ...s, [z.id]: { ...e, vulnerability: Number(v) } }))} /></Table.Td>
              <Table.Td ta="right">{fmt(z.water_customers)}</Table.Td>
              <Table.Td>{dirty && <Button size="compact-xs" onClick={() => save.mutate({ id: z.id, body: e })}>Save</Button>}</Table.Td>
            </Table.Tr>);
        })}</Table.Tbody>
      </Table>
      <Text size="xs" c="dimmed" p="sm">Vulnerability (0.1–1.0) combines overhead exposure, tree canopy and surge risk; it drives the outage prediction for the zone.</Text>
    </Card>
  );
}

function Integrations() {
  const { data } = useGet<{ connector_mode: string; openweather: { configured: boolean; from_env: boolean; masked: string } }>("/admin/integrations");
  const wx = useGet<Weather>("/weather");
  const [key, setKey] = useState("");
  const save = useAction((body: object) => api.put<{ weather?: Weather }>("/admin/integrations", body), { success: "Integration settings saved", invalidate: ["/admin", "/weather"] });
  if (!data) return <Loading />;
  return (
    <Grid gutter="lg">
      <Grid.Col span={{ base: 12, lg: 6 }}>
        <Card h="100%">
          <Group justify="space-between" mb="xs"><Text fw={600}>OMS / AMI outage feed</Text><Badge color={data.connector_mode === "off" ? "gray" : "teal"}>{data.connector_mode === "off" ? "Off" : "Sandbox"}</Badge></Group>
          <Text size="sm" c="dimmed" mb="md">Creates outage tickets from smart-meter last-gasp events and SCADA trips, and receives crew status from the field mobile app.
            Sandbox mode emulates both for training and demonstrations; production connects to the utility's OMS (MultiSpeak / REST).</Text>
          <SegmentedControl value={data.connector_mode} onChange={v => save.mutate({ connector_mode: v })} data={[{ value: "sandbox", label: "Sandbox" }, { value: "off", label: "Off" }]} />
        </Card>
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 6 }}>
        <Card h="100%">
          <Group justify="space-between" mb="xs"><Group gap={6}><IconCloud size={18} /><Text fw={600}>Weather</Text></Group>
            {!wx.data || wx.data.error ? <Badge color="red">Unavailable</Badge>
              : wx.data.key_error ? <Badge color="yellow">Open-Meteo (fallback)</Badge>
              : <Badge color="teal">{wx.data.source} connected</Badge>}</Group>
          <Text size="sm" c="dimmed" mb="md">Open-Meteo is used without a key. Add a free OpenWeather key for OpenWeather data and radar map overlays. The key stays on the server.</Text>
          <Group align="flex-end" gap="xs">
            <PasswordInput style={{ flex: 1 }} label="OpenWeather API key" placeholder={data.openweather.masked || "Paste key"} value={key} onChange={e => setKey(e.currentTarget.value)} />
            <Button disabled={!key.trim()} loading={save.isPending} onClick={async () => { await save.mutateAsync({ openweather_key: key }); setKey(""); }}>Save & test</Button>
            {data.openweather.masked && <Button variant="default" onClick={() => save.mutate({ openweather_key: "" })}>Remove</Button>}
          </Group>
          {wx.data?.error && <Alert color="red" mt="sm" p="xs">{wx.data.error}. New OpenWeather keys can take up to 2 hours to activate.</Alert>}
          {wx.data && !wx.data.error && wx.data.key_error && <Alert color="yellow" mt="sm" p="xs">
            The OpenWeather key isn't working ({wx.data.key_error}). Weather is coming from Open-Meteo in the meantime, and radar overlays are off.
            New OpenWeather keys can take up to 2 hours to activate. Paste it again and use Save & test to retry.</Alert>}
          {wx.data && !wx.data.error && <Text size="xs" c="dimmed" mt="sm">Tampa now: {Math.round(wx.data.temp_f)}°F, {wx.data.description}, wind {Math.round(wx.data.wind_mph)} mph · updated {ago(wx.data.updated_at)}</Text>}
        </Card>
      </Grid.Col>
      <Grid.Col span={12}>
        <Card padding={0}>
          <Table>
            <Table.Thead><Table.Tr><Table.Th>System</Table.Th><Table.Th>Purpose</Table.Th><Table.Th>Status</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{[
              ["National Hurricane Center", "Active storm positions and intensity (CurrentStorms.json)", "Live"],
              ["Weather", "Current conditions & forecast for the service territory", !wx.data || wx.data.error ? "Unavailable" : wx.data.key_error ? "Live (Open-Meteo fallback)" : "Live"],
              ["OMS / AMI / SCADA", "Outage intake and restoration confirmation", data.connector_mode === "off" ? "Off" : "Sandbox"],
              ["Field mobile app", "Crew acceptance, on-site and restored updates", data.connector_mode === "off" ? "Off" : "Sandbox"],
              ["SMS / email / IVR gateway", "Customer notifications", "Sandbox"], ["X / Facebook", "Social posting after approval", "Sandbox"],
              ["Public website", "Outage map and ETR lookup at /outage-map", "Live"],
            ].map(([n, p, s]) => <Table.Tr key={n}><Table.Td fw={500}>{n}</Table.Td><Table.Td><Text size="sm" c="dimmed">{p}</Text></Table.Td>
              <Table.Td><Badge color={s === "Live" ? "teal" : s === "Off" || s === "Unavailable" ? "gray" : "yellow"}>{s}</Badge></Table.Td></Table.Tr>)}
            </Table.Tbody>
          </Table>
        </Card>
      </Grid.Col>
    </Grid>
  );
}

function AuditLog() {
  const [q, setQ] = useState("");
  const [dq] = useDebouncedValue(q, 300);
  const [action, setAction] = useState<string | null>(null);
  const { data } = useGet<Audit[]>(`/admin/audit${qs({ q: dq, action })}`);
  return (
    <Card padding={0}>
      <Group p="sm" gap="sm">
        <TextInput placeholder="Search detail or user" leftSection={<IconSearch size={16} />} value={q} onChange={e => setQ(e.currentTarget.value)} w={260} />
        <Select placeholder="Action" clearable value={action} onChange={setAction} w={200}
          data={["event", "prediction", "recommendation", "outage", "mutual_aid", "message", "etr", "user", "auth", "integration"].map(a => ({ value: a, label: a }))} />
      </Group>
      {!data ? <Loading /> : (
        <Table.ScrollContainer minWidth={800} mah={620}>
          <Table stickyHeader>
            <Table.Thead><Table.Tr><Table.Th>When</Table.Th><Table.Th>User</Table.Th><Table.Th>Action</Table.Th><Table.Th>Detail</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{data.map(a => (
              <Table.Tr key={a.id}><Table.Td><Text size="sm">{dt(a.at)}</Text></Table.Td><Table.Td>{a.user}</Table.Td><Table.Td><Badge variant="outline" color="gray">{a.action}</Badge></Table.Td>
                <Table.Td><Text size="sm">{a.detail}</Text></Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Card>
  );
}
