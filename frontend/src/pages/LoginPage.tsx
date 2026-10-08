import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Alert, Anchor, Badge, Box, Button, Divider, Group, Image, Menu, PasswordInput, SimpleGrid, Stack, Text, TextInput, UnstyledButton } from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useQuery } from "@tanstack/react-query";
import { IconAlertTriangle, IconArrowUp, IconBolt, IconChevronDown, IconLock, IconLogin2, IconPlug, IconSparkles } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const LOGO = "https://d7umqicpi7263.cloudfront.net/img/product/f93e9a80-bf37-4444-9934-14f54d16daef.com/3b20a3af2ab95662337f13eca910ef71";
const DEMO_EMAIL = "steve@powerconnect.ai";
const DEMO_PASSWORD = "admin";
// passwords of the demo admins (backend DEMO_ADMINS); every seeded Bayview role account uses ROLE_PASSWORD
const DEMO_PASSWORDS: Record<string, string> = { [DEMO_EMAIL]: DEMO_PASSWORD, "admin@gmail.com": "admin@123" };
const ROLE_PASSWORD = "oms360";

const FEATURES = [
  { icon: IconBolt, label: "Real-time AI predictions", color: "linear-gradient(135deg,#ffb547,#ff8a1f)" },
  { icon: IconPlug, label: "Works with your OMS", color: "linear-gradient(135deg,#4d8dff,#2b6bff)" },
  { icon: IconLock, label: "Enterprise security", color: "linear-gradient(135deg,#a68cfa,#7c5cf0)" },
];

function MicrosoftLogo() {
  return (
    <svg width="16" height="16" viewBox="0 0 21 21" aria-hidden>
      <rect x="1" y="1" width="9" height="9" fill="#f25022" /><rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" /><rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState("");
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: { email: (v: string) => (/\S+@\S+/.test(v) ? null : "Enter your work email"), password: (v: string) => (v ? null : "Enter your password") },
  });
  const [waking, setWaking] = useState(false);
  // also wakes a sleeping free-tier server as soon as the page opens
  const accounts = useQuery({ queryKey: ["sandbox"], queryFn: () => api.get<{ email: string; name: string; role: string; title: string }[]>("/auth/sandbox-accounts"), retry: 6 });
  if (user) return <Navigate to={(loc.state as { from?: string })?.from ?? "/"} replace />;

  const submit = form.onSubmit(async v => {
    setBusy(true); setError(null);
    const slow = setTimeout(() => setWaking(true), 4000);
    try { await login(v.email, v.password); nav("/"); } catch (e) { setError((e as Error).message); } finally { clearTimeout(slow); setWaking(false); setBusy(false); }
  });
  const askTeaser = () => {
    if (!question.trim()) return;
    notifications.show({ color: "brand", title: "Sign in to ask the AI Assistant", message: "The AI Assistant answers from live storm, ticket and crew data once you're signed in." });
  };

  return (
    <Box className="login-shell" style={{ backgroundImage: "url(/login-bg.webp)" }}>
      <div className="login-shade" />
      <Group className="login-grid" align="center" justify="space-between" wrap="wrap" gap={48}>
        {/* ---- left: product story */}
        <Stack gap="xl" maw={780} className="login-story">
          <h1 className="login-title">
            Intelligent <span className="grad-a">Storm Outage</span><br />
            <span className="grad-b">Management</span> Platform
          </h1>
          <Text className="login-lead">
            AI on top of the outage management system you already run. Predict storm impact before landfall, size crews,
            and give every customer a restoration time they can trust.
          </Text>
          <SimpleGrid cols={{ base: 1, xs: 3 }} spacing="md">
            {FEATURES.map(f => (
              <div key={f.label} className="glass-tile">
                <div className="tile-icon" style={{ background: f.color }}><f.icon size={18} color="white" /></div>
                <Text fw={600} c="#0b1532" size="sm">{f.label}</Text>
              </div>
            ))}
          </SimpleGrid>
          <div className="glass-tile assistant">
            <Group gap={8}>
              <IconSparkles size={15} color="#2b6bff" />
              <Text fw={600} size="sm" c="#0b1532">AI Assistant</Text>
              <Badge size="sm" variant="filled" color="brand">BETA</Badge>
            </Group>
            <Text c="#33405f" mt={6} mb="xl">How can I help you today?</Text>
            <Group className="assistant-input" wrap="nowrap" gap={8}>
              <input placeholder="When will power be back in Brandon?" value={question} onChange={e => setQuestion(e.currentTarget.value)}
                onKeyDown={e => e.key === "Enter" && askTeaser()} aria-label="Ask the assistant" />
              <Button size="xs" radius="md" leftSection={<IconArrowUp size={14} />} onClick={askTeaser}>Send</Button>
            </Group>
          </div>
        </Stack>

        {/* ---- right: sign-in card */}
        <div className="login-card">
          <Group justify="center" mb="md"><Image src={LOGO} h={46} w="auto" fit="contain" alt="PowerConnect.AI" /></Group>
          <Text ta="center" fw={600} size="lg" c="#0b1532" mb="lg">Sign in with your account</Text>
          <form onSubmit={submit}>
            <Stack gap="sm">
              {error && <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} p="xs">{error}</Alert>}
              <TextInput label="EMAIL" size="md" radius="md" autoComplete="username" classNames={{ label: "login-label", input: "login-input" }} {...form.getInputProps("email")} />
              <PasswordInput label="PASSWORD" size="md" radius="md" autoComplete="current-password" classNames={{ label: "login-label", input: "login-input", innerInput: "login-inner" }} {...form.getInputProps("password")} />
              <Group justify="flex-end">
                <Anchor size="sm" c="#33405f" component="button" type="button"
                  onClick={() => notifications.show({ title: "Password reset", message: "Ask your OMS360 administrator to reset your password (profile menu → Administration → Users)." })}>Forgot password?</Anchor>
              </Group>
              <Button type="submit" size="md" radius="md" loading={busy} leftSection={<IconLogin2 size={18} />} fullWidth className="login-btn">Sign in</Button>
              {waking && <Text ta="center" size="xs" c="#33405f">Waking up the server — this can take up to a minute after a quiet period…</Text>}
            </Stack>
          </form>
          <Divider my="lg" label={<Text size="xs" fw={600} c="#33405f" style={{ letterSpacing: ".12em" }}>OR CONTINUE WITH</Text>} labelPosition="center" color="rgba(11,21,50,.18)" />
          <Button fullWidth size="md" radius="md" variant="white" color="dark" leftSection={<MicrosoftLogo />} className="ms-btn"
            onClick={() => notifications.show({ title: "Microsoft sign-in", message: "Single sign-on with Microsoft Entra ID is configured per utility. Use your email and password in this sandbox." })}>
            Sign in with Microsoft
          </Button>
          <Divider my="lg" color="rgba(11,21,50,.12)" />
          <Group justify="center" gap={6}><Image src={LOGO} h={26} w="auto" fit="contain" alt="" /></Group>
          <Text ta="center" size="sm" c="#33405f" mt={6}>
            Demo: <b>{DEMO_EMAIL}</b> / <b>{DEMO_PASSWORD}</b>
          </Text>
          <Text ta="center" size="sm" c="#33405f">
            Admin: <b>admin@gmail.com</b> / <b>admin@123</b>
          </Text>
          {!!accounts.data?.length && (
            <Group justify="center" mt={6}>
              <Menu position="top" width={300} shadow="md">
                <Menu.Target>
                  <UnstyledButton style={{ color: "#33405f", fontSize: 12 }}><Group gap={2}>Other demo roles <IconChevronDown size={12} /></Group></UnstyledButton>
                </Menu.Target>
                <Menu.Dropdown>
                  {accounts.data.filter(a => a.email !== DEMO_EMAIL).map(a => (
                    <Menu.Item key={a.email} onClick={() => form.setValues({ email: a.email, password: DEMO_PASSWORDS[a.email] ?? ROLE_PASSWORD })}
                      rightSection={<Badge size="xs" variant="light">{a.role}</Badge>}>
                      <Text size="sm">{a.name}</Text><Text size="xs" c="dimmed">{a.title}</Text>
                    </Menu.Item>
                  ))}
                </Menu.Dropdown>
              </Menu>
            </Group>
          )}
        </div>
      </Group>
      <Text className="login-foot">OMS 360 · <Anchor href="/outage-map" c="inherit" size="xs" underline="always">Public outage map</Anchor> · demo</Text>
    </Box>
  );
}
