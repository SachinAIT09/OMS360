import { Badge, Button, Card, Collapse, Group, Stack, Text, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconCheck, IconChevronDown, IconSparkles, IconX } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction } from "../api/hooks";
import type { Recommendation } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ago } from "../lib/format";
import { PriorityBadge } from "./badges";

export function RecommendationCard({ r }: { r: Recommendation }) {
  const { can } = useAuth();
  const [open, { toggle }] = useDisclosure(false);
  const approve = useAction(() => api.post<Recommendation>(`/recommendations/${r.id}/approve`), { success: x => x.outcome || "Approved" });
  const dismiss = useAction(() => api.post(`/recommendations/${r.id}/dismiss`), { success: "Recommendation dismissed" });
  const decided = r.status !== "open";
  const border = r.priority === "Critical" ? "var(--mantine-color-red-6)" : r.priority === "High" ? "var(--mantine-color-orange-6)" : "var(--mantine-color-gray-6)";
  return (
    <Card padding="sm" style={{ borderLeft: `3px solid ${decided ? "var(--mantine-color-teal-6)" : border}`, opacity: decided ? 0.7 : 1 }}>
      <Group gap="xs" wrap="nowrap" align="flex-start">
        <PriorityBadge priority={r.priority} size="sm" />
        <Text size="sm" fw={600} style={{ flex: 1 }}>{r.title}</Text>
      </Group>
      {r.detail && <Text size="xs" c="dimmed" mt={6}>{r.detail}</Text>}
      {r.impact && <Group gap={4} mt={6}><IconSparkles size={13} color="var(--mantine-color-ai-4)" /><Text size="xs" c="ai.3" fw={500}>{r.impact}</Text></Group>}
      {r.why && <>
        <UnstyledButton onClick={toggle} mt={6}><Group gap={4}><Text size="xs" c="dimmed">Why this recommendation?</Text><IconChevronDown size={12} style={{ transform: open ? "rotate(180deg)" : undefined }} /></Group></UnstyledButton>
        <Collapse in={open}><Text size="xs" c="dimmed" mt={4}>{r.why}</Text></Collapse>
      </>}
      <Group justify="space-between" mt="sm">
        {decided
          ? <Stack gap={0}><Badge color={r.status === "approved" ? "teal" : "gray"} size="sm">{r.status} by {r.decided_by}</Badge>
              <Text size="xs" c="dimmed" mt={2}>{r.outcome || ""} {ago(r.decided_at)}</Text></Stack>
          : <Text size="xs" c="dimmed">Suggested {ago(r.created_at)}</Text>}
        {!decided && can("recommendations.decide") && (
          <Group gap={6}>
            <Button size="compact-sm" variant="subtle" color="gray" leftSection={<IconX size={14} />} loading={dismiss.isPending} onClick={() => dismiss.mutate()}>Dismiss</Button>
            <Button size="compact-sm" leftSection={<IconCheck size={14} />} loading={approve.isPending} onClick={() => approve.mutate()}>Approve</Button>
          </Group>
        )}
      </Group>
    </Card>
  );
}
