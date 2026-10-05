import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useEvents } from "../api/hooks";
import type { StormEvent } from "../api/types";

/** The storm event the operator is working on (top-bar switcher). Remembered per browser. */
interface EventCtx { event: StormEvent | null; events: StormEvent[]; setEventId: (id: number) => void }
const Ctx = createContext<EventCtx>({ event: null, events: [], setEventId: () => undefined });
export const useCurrentEvent = () => useContext(Ctx);

const KEY = "oms360_event";

export function EventProvider({ children }: { children: ReactNode }) {
  const { data: events = [] } = useEvents();
  const [id, setId] = useState<number | null>(() => { try { return Number(localStorage.getItem(KEY)) || null; } catch { return null; } });

  const event = useMemo(() => {
    const chosen = events.find(e => e.id === id);
    return chosen ?? events.find(e => e.status !== "closed") ?? events[0] ?? null;
  }, [events, id]);

  useEffect(() => { if (event && event.id !== id) setId(event.id); }, [event, id]);

  const setEventId = (v: number) => { setId(v); try { localStorage.setItem(KEY, String(v)); } catch { /* storage blocked */ } };
  return <Ctx.Provider value={{ event, events, setEventId }}>{children}</Ctx.Provider>;
}
