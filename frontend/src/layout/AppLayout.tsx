import { useEffect, useRef, useState } from "react";
import { Navigate, NavLink as RouterLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  ActionIcon, AppShell, Avatar, Badge, Box, Burger, Center, Divider, Group, Image, Indicator, Loader, Menu, NavLink, ScrollArea,
  Select, Stack, Text, Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
import { Spotlight, type SpotlightActionData } from "@mantine/spotlight";
import {
  IconBell, IconBolt, IconBrain, IconBroadcast, IconChartBar, IconCloudStorm, IconExternalLink, IconLayoutDashboard, IconLogout, IconMoon,
  IconSearch, IconSettings, IconSun, IconTool, IconTruck,
} from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { invalidate, useGet } from "../api/hooks";
import type { Message, Recommendation, Weather } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { EventProvider, useCurrentEvent } from "../auth/EventContext";
import { EventStatusBadge } from "../components/badges";
import { useLiveUpdates } from "../lib/live";

const LOGO = "https://d7umqicpi7263.cloudfront.net/img/product/f93e9a80-bf37-4444-9934-14f54d16daef.com/3b20a3af2ab95662337f13eca910ef71";

const NAV = [
  { group: "Operations", items: [
    { to: "/", label: "Overview", icon: IconLayoutDashboard },
    { to: "/events", label: "Storm Events", icon: IconCloudStorm },
    { to: "/outages", label: "Outages", icon: IconBolt },
    { to: "/restoration", label: "Restoration & ETR", icon: IconTool },
  ] },
  { group: "Field", items: [{ to: "/crews", label: "Crews & Mutual Aid", icon: IconTruck }] },
  { group: "Customers", items: [{ to: "/communications", label: "Communications", icon: IconBroadcast }] },
  { group: "Intelligence", items: [
    { to: "/jarvis", label: "AI Assistant", icon: IconBrain },
    { to: "/reports", label: "Reports", icon: IconChartBar },
  ] },
];

export function AppLayout() {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <Center h="100vh"><Loader /></Center>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <EventProvider><Shell /></EventProvider>;
}

const NAV_WIDTH = 248;
const RAIL_WIDTH = 68;
// One curve for the nav width and the page padding so both move as a single surface.
const NAV_MS = 280;
const NAV_EASE = "cubic-bezier(0.22, 1, 0.36, 1)";

function Shell() {
  const [opened, { toggle, close }] = useDisclosure();
  const { user } = useAuth();
  const loc = useLocation();
  const qc = useQueryClient();
  useLiveUpdates(true);
  // Each app load (page reload or sign-in) tops the demo storm back up to a full set of sample data; a no-op outside sandbox mode.
  useEffect(() => {
    api.post<{ outages: number; messages: number }>("/demo/refresh")
      .then(r => { if (r.outages || r.messages) invalidate(qc, [""]); })
      .catch(() => { /* demo top-up is best-effort */ });
  }, [qc]);
  const desktop = useMediaQuery("(min-width: 48em)") ?? true;
  // Desktop: the nav rests as an icon rail and widens while hovered (or tabbed into), pushing the page over; leaving closes it.
  // Short intent delays stop it flickering when the pointer only brushes past.
  const [peek, setPeek] = useState(false);
  const peekTimer = useRef<number>();
  const schedulePeek = (open: boolean, ms: number) => { window.clearTimeout(peekTimer.current); peekTimer.current = window.setTimeout(() => setPeek(open), ms); };
  const startPeek = () => schedulePeek(true, 90);
  const endPeek = () => schedulePeek(false, 140);
  useEffect(() => () => window.clearTimeout(peekTimer.current), []);
  const expanded = !desktop || peek;

  return (
    <AppShell header={{ height: 58 }} navbar={{ width: { base: NAV_WIDTH, sm: peek ? NAV_WIDTH : RAIL_WIDTH }, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="lg" transitionDuration={NAV_MS} transitionTimingFunction={NAV_EASE}>
      <AppShell.Header>
        <Group h="100%" px="md" gap="sm" wrap="nowrap">
          <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
          <Brand />
          <EventSwitcher />
          <Box style={{ flex: 1 }} />
          <SearchButton />
          <WeatherChip />
          <Bell />
          <ThemeToggle />
          <UserMenu />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p={10} className={`app-nav${desktop ? " collapsible" : ""}${expanded ? " expanded" : ""}`}
        style={{ "--nav-ms": `${NAV_MS}ms`, "--nav-ease": NAV_EASE } as React.CSSProperties}
        onMouseEnter={desktop ? startPeek : undefined} onMouseLeave={desktop ? endPeek : undefined}
        onFocus={desktop ? e => { if ((e.target as HTMLElement).matches(":focus-visible")) setPeek(true); } : undefined}
        onBlur={desktop ? e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) endPeek(); } : undefined}>
        <AppShell.Section grow component={ScrollArea} scrollbars="y">
          {NAV.map(g => (
            <Box key={g.group} mb="sm">
              <NavGroupTitle>{g.group}</NavGroupTitle>
              {g.items.map(it => (
                <NavLink key={it.to} component={RouterLink} to={it.to} label={it.label} leftSection={<it.icon size={18} stroke={1.6} />}
                  active={it.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(it.to)} onClick={close} style={{ borderRadius: 8 }} />
              ))}
            </Box>
          ))}
        </AppShell.Section>
        <AppShell.Section>
          <Divider mb="sm" />
          <NavLink component="a" href="/outage-map" target="_blank" label="Public outage map" description="bayviewpw.example/outages"
            leftSection={<IconExternalLink size={18} stroke={1.6} />} style={{ borderRadius: 8 }} />
          <Text size="xs" c="dimmed" px={14} mt="xs" truncate className="app-nav-fade">Bayview Power & Water · {user?.role_label}</Text>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}

/** Same height in both states: the text fades out on the rail and a short rule fades in, so nothing below it moves. */
function NavGroupTitle({ children }: { children: string }) {
  return <Text size="xs" fw={600} c="dimmed" tt="uppercase" px={14} mb={4} className="app-nav-group" style={{ letterSpacing: ".08em" }}><span>{children}</span></Text>;
}

function Brand() {
  return (
    <UnstyledButton component={RouterLink} to="/" visibleFrom="sm" style={{ width: 216 }}>
      <Group gap={10} wrap="nowrap">
        <Box bg="white" p={4} style={{ borderRadius: 6, lineHeight: 0 }}>
          <Image src={LOGO} h={22} w="auto" fit="contain" alt="PowerConnect" fallbackSrc="data:image/gif;base64,R0lGODlhAQABAAAAACw=" />
        </Box>
        <Text fw={700} size="lg">OMS<Text span c="brand.4" inherit>360</Text></Text>
      </Group>
    </UnstyledButton>
  );
}

function EventSwitcher() {
  const { event, events, setEventId } = useCurrentEvent();
  if (!events.length) return null;
  return (
    <Group gap="xs" wrap="nowrap">
      <Select size="sm" w={250} value={event ? String(event.id) : null} onChange={v => v && setEventId(Number(v))} allowDeselect={false}
        data={[
          { group: "Open events", items: events.filter(e => e.status !== "closed").map(e => ({ value: String(e.id), label: e.name })) },
          { group: "Closed", items: events.filter(e => e.status === "closed").map(e => ({ value: String(e.id), label: e.name })) },
        ].filter(g => g.items.length)}
        leftSection={<IconCloudStorm size={16} />} aria-label="Storm event" />
      {event && <EventStatusBadge status={event.status} />}
    </Group>
  );
}

function SearchButton() {
  const [q, setQ] = useState("");
  const go = useNavigate();
  const { data = [], isFetching } = useGet<{ type: string; id: number; label: string; sub: string }[]>(q.trim().length >= 2 ? `/search?q=${encodeURIComponent(q.trim())}` : null);
  const pages: SpotlightActionData[] = [
    ["/", "Overview"], ["/events", "Storm events"], ["/outages", "Outages"], ["/restoration", "Restoration & ETR"], ["/crews", "Crews & mutual aid"],
    ["/communications", "Communications"], ["/jarvis", "AI Assistant"], ["/reports", "Reports"],
  ].map(([to, l]) => ({ id: `p${to}`, label: l, description: "Go to page", onClick: () => go(to) }));
  const results: SpotlightActionData[] = data.map(r => ({
    id: `${r.type}${r.id}`, label: r.label, description: `${r.type} · ${r.sub}`,
    onClick: () => go(r.type === "outage" ? `/outages?open=${r.id}` : r.type === "crew" ? `/crews?q=${r.label}` : `/events/${r.id}`),
  }));
  return (
    <>
      <Spotlight actions={q.trim().length >= 2 ? results : pages} query={q} onQueryChange={setQ} shortcut={["mod + K", "/"]} filter={(_, a) => a}
        nothingFound={isFetching ? "Searching…" : "Nothing found"} searchProps={{ leftSection: <IconSearch size={18} />, placeholder: "Ticket number, feeder, crew code, event…" }} />
    </>
  );
}

function WeatherChip() {
  const { data } = useGet<Weather>("/weather", { refetchInterval: 600_000 });
  if (!data || data.error) return null;
  return (
    <Tooltip label={`Live weather · Tampa · ${data.source}`}>
      <Badge variant="outline" color="teal" size="lg" leftSection={<span className="pulse-dot" />} visibleFrom="lg" style={{ textTransform: "none" }}>
        Tampa {Math.round(data.temp_f)}°F · {Math.round(data.wind_mph)} mph
      </Badge>
    </Tooltip>
  );
}

function Bell() {
  const { event } = useCurrentEvent();
  const go = useNavigate();
  const recs = useGet<Recommendation[]>(event ? `/events/${event.id}/recommendations` : null);
  const msgs = useGet<Message[]>(event ? `/messages?event_id=${event.id}&status=pending` : null);
  const openRecs = (recs.data ?? []).filter(r => r.status === "open");
  const n = openRecs.length + (msgs.data?.length ?? 0);
  return (
    <Menu width={340} position="bottom-end" shadow="md">
      <Menu.Target>
        <Indicator label={n} size={16} disabled={!n} color="red" offset={4}>
          <ActionIcon variant="subtle" size="lg" aria-label="Notifications"><IconBell size={20} stroke={1.6} /></ActionIcon>
        </Indicator>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Needs your decision</Menu.Label>
        {openRecs.slice(0, 5).map(r => (
          <Menu.Item key={r.id} onClick={() => go("/")} leftSection={<Badge size="xs" color={r.priority === "Critical" ? "red" : "orange"}>{r.priority}</Badge>}>
            <Text size="sm" lineClamp={2}>{r.title}</Text>
          </Menu.Item>
        ))}
        {!!msgs.data?.length && <Menu.Item onClick={() => go("/communications?tab=pending")}>{msgs.data.length} message{msgs.data.length > 1 ? "s" : ""} waiting for approval</Menu.Item>}
        {!n && <Text size="sm" c="dimmed" p="sm">You're all caught up.</Text>}
      </Menu.Dropdown>
    </Menu>
  );
}

function ThemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("dark");
  return (
    <ActionIcon variant="subtle" size="lg" onClick={() => setColorScheme(scheme === "dark" ? "light" : "dark")} aria-label="Toggle colour scheme">
      {scheme === "dark" ? <IconSun size={19} stroke={1.6} /> : <IconMoon size={19} stroke={1.6} />}
    </ActionIcon>
  );
}

function UserMenu() {
  const { user, logout, can } = useAuth();
  const go = useNavigate();
  const loc = useLocation();
  if (!user) return null;
  const initials = user.name.split(" ").map(w => w[0]).join("").slice(0, 2);
  return (
    <Menu position="bottom-end" width={240} shadow="md">
      <Menu.Target>
        <UnstyledButton>
          <Group gap={8} wrap="nowrap">
            <Avatar color="brand" radius="xl" size={32}>{initials}</Avatar>
            <Stack gap={0} visibleFrom="md">
              <Text size="sm" fw={500} lh={1.2}>{user.name}</Text>
              <Text size="xs" c="dimmed" lh={1.2}>{user.role_label}</Text>
            </Stack>
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Box px="sm" py={6}>
          <Text size="sm" fw={600} truncate>{user.name}</Text>
          <Text size="xs" c="dimmed" truncate>{user.email}</Text>
          {user.title && <Text size="xs" c="dimmed" truncate>{user.title}</Text>}
        </Box>
        {can("admin") && <>
          <Menu.Divider />
          <Menu.Item leftSection={<IconSettings size={16} />} onClick={() => go("/admin")}
            color={loc.pathname.startsWith("/admin") ? "brand" : undefined}>Administration</Menu.Item>
        </>}
        <Menu.Divider />
        <Menu.Item color="red" leftSection={<IconLogout size={16} />} onClick={logout}>Sign out</Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
