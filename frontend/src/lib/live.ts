import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { tokenStore } from "../api/client";
import { invalidate } from "../api/hooks";

/** Which cached endpoints each server event makes stale. */
const AFFECTS: Record<string, string[]> = {
  outages: ["/outages", "/events", "/crews", "/reports", "/public"],
  crews: ["/crews", "/staging-yards", "/events"],
  mutual_aid: ["/mutual-aid", "/crews", "/events"],
  messages: ["/messages", "/events"],
  events: ["/events", "/reports"],
  predictions: ["/events"],
  recommendations: ["/events", "/tasks", "/mutual-aid", "/messages", "/crews"],
  restoration: ["/events", "/public"],
  tasks: ["/tasks", "/events"],
  activity: ["/events"],
};

/** Server-sent events: keeps every screen current without manual refresh. */
export function useLiveUpdates(enabled: boolean) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    let es: EventSource | null = null;
    let timer: number | undefined;
    const pending = new Set<string>();
    const flush = () => { invalidate(qc, [...pending]); pending.clear(); timer = undefined; };

    const connect = () => {
      es = new EventSource(`/api/stream?token=${encodeURIComponent(tokenStore.get() ?? "")}`);
      es.onmessage = ev => {
        try {
          const msg = JSON.parse(ev.data) as { type: string; created?: number; detail?: string };
          (AFFECTS[msg.type] ?? []).forEach(p => pending.add(p));
          if (msg.type === "outages" && msg.created) {
            notifications.show({ id: "intake", color: "orange", title: "New outages", message: `${msg.created} new ticket${msg.created > 1 ? "s" : ""} from OMS / AMI`, autoClose: 2500 });
          }
          if (!timer) timer = window.setTimeout(flush, 400); // batch bursts
        } catch { /* ignore malformed */ }
      };
      es.onerror = () => { es?.close(); window.setTimeout(connect, 5000); };
    };
    connect();
    return () => { es?.close(); if (timer) clearTimeout(timer); };
  }, [enabled, qc]);
}
