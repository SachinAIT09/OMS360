import { Button, Group, Text } from "@mantine/core";
import { modals } from "@mantine/modals";
import { IconArrowRight } from "@tabler/icons-react";
import { api } from "../api/client";
import { useAction } from "../api/hooks";
import type { StormEvent } from "../api/types";
import { useAuth } from "../auth/AuthContext";

const NEXT: Record<string, { to: string; label: string; color: string; explain: string }[]> = {
  monitoring: [{ to: "preparing", label: "Start preparing", color: "yellow", explain: "Opens preparation: crews, mutual aid, materials and customer comms." }],
  preparing: [{ to: "active", label: "Activate event", color: "red", explain: "Outage intake from OMS/AMI will be tracked against this storm. Do this when the storm begins affecting the territory." }],
  active: [{ to: "restoring", label: "Move to restoration", color: "blue", explain: "Winds are below crew-safety limits and field restoration is the focus." }],
  restoring: [{ to: "closed", label: "Close event", color: "gray", explain: "Freezes the event for reporting. Make sure every ticket is restored or cancelled." }],
  closed: [],
};

export function EventLifecycle({ event }: { event: StormEvent }) {
  const { can } = useAuth();
  const change = useAction((to: string) => api.post(`/events/${event.id}/status`, { status: to }), { success: "Event status updated" });
  if (!can("events.manage")) return null;
  return (
    <Group gap="xs">
      {NEXT[event.status].map(n => (
        <Button key={n.to} color={n.color} rightSection={<IconArrowRight size={16} />} loading={change.isPending}
          onClick={() => modals.openConfirmModal({
            title: `${n.label}: ${event.name}`, children: <Text size="sm">{n.explain}</Text>,
            labels: { confirm: n.label, cancel: "Cancel" }, confirmProps: { color: n.color }, onConfirm: () => change.mutate(n.to),
          })}>{n.label}</Button>
      ))}
    </Group>
  );
}
