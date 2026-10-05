import type { ReactNode } from "react";
import { Alert, Card, Center, Group, Loader, Progress, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconAlertTriangle, IconInbox } from "@tabler/icons-react";

export function PageHeader({ title, description, actions, badge }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; badge?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="lg" wrap="wrap" gap="sm">
      <Stack gap={2}>
        <Group gap="sm"><Title order={2} fz={24}>{title}</Title>{badge}</Group>
        {description && <Text c="dimmed" size="sm">{description}</Text>}
      </Stack>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  );
}

export function Stat({ label, value, hint, color, icon, progress, onClick }: {
  label: string; value: ReactNode; hint?: ReactNode; color?: string; icon?: ReactNode; progress?: number; onClick?: () => void;
}) {
  return (
    <Card padding="md" onClick={onClick} style={onClick ? { cursor: "pointer" } : undefined}>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: ".06em" }}>{label}</Text>
        {icon && <ThemeIcon variant="light" color={color ?? "brand"} size="md" radius="md">{icon}</ThemeIcon>}
      </Group>
      <Text fz={26} fw={700} mt={4} c={color && color !== "brand" ? `${color}.5` : undefined} className="tabular" lh={1.2}>{value}</Text>
      {hint && <Text size="xs" c="dimmed" mt={4}>{hint}</Text>}
      {progress != null && <Progress value={Math.min(100, progress * 100)} size="sm" mt="sm" color={color ?? "brand"} />}
    </Card>
  );
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <Center py="xl">
      <Stack align="center" gap="xs" maw={420}>
        <ThemeIcon size={44} radius="xl" variant="light" color="gray">{icon ?? <IconInbox size={24} />}</ThemeIcon>
        <Text fw={600}>{title}</Text>
        {children && <Text size="sm" c="dimmed" ta="center">{children}</Text>}
      </Stack>
    </Center>
  );
}

export function Loading() {
  return <Center py={80}><Loader /></Center>;
}

export function ErrorState({ error }: { error: Error | null }) {
  return <Alert color="red" icon={<IconAlertTriangle />} title="Couldn't load this page">{error?.message ?? "Unknown error"}</Alert>;
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return <Group justify="space-between" mb="sm"><Text fw={600}>{children}</Text>{right}</Group>;
}

/** Renders **bold** segments without injecting HTML. */
export function Rich({ text }: { text: string }) {
  return <>{text.split(/\*\*(.+?)\*\*/g).map((p, i) => (i % 2 ? <b key={i}>{p}</b> : p))}</>;
}
