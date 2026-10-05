import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box, Button, Group, Paper, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { invalidate } from "../api/hooks";
import type { JarvisAction, JarvisMessage } from "../api/types";
import { Rich } from "./common";

type SR = { lang: string; interimResults: boolean; start: () => void; onresult: (e: any) => void; onerror: (e: any) => void; onend: () => void };
const SpeechRecognition: (new () => SR) | undefined = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export function speak(text: string, onStart?: () => void, onEnd?: () => void) {
  if (!("speechSynthesis" in window) || !text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const voices = speechSynthesis.getVoices();
  const v = voices.find(v => /en-GB/.test(v.lang) && /male|daniel|george|arthur/i.test(v.name)) || voices.find(v => /en-(GB|US)/.test(v.lang));
  if (v) u.voice = v;
  u.rate = 1.03;
  u.onstart = () => onStart?.();
  u.onend = () => onEnd?.();
  speechSynthesis.speak(u);
}


/** Runs an answer's action button: navigate, or approve a recommendation. */
export function useAssistantAction() {
  const qc = useQueryClient();
  const go = useNavigate();
  return async (a: JarvisAction) => {
    if (a.kind === "nav") { go(String(a.value)); return; }
    try {
      const r = await api.post<{ outcome: string }>(`/recommendations/${a.value}/approve`);
      notifications.show({ color: "teal", message: r.outcome || "Approved" });
      invalidate(qc, ["/events", "/mutual-aid", "/messages", "/crews", "/outages", "/tasks"]);
    } catch (e) { notifications.show({ color: "red", message: (e as Error).message }); }
  };
}

/** Browser speech-to-text: streams the transcript to `onText` and hands the final phrase to `onFinal`. */
export function useVoiceInput(onText: (t: string) => void, onFinal: (t: string) => void) {
  const [listening, setListening] = useState(false);
  const listen = () => {
    if (!SpeechRecognition) { notifications.show({ message: "Voice input needs Chrome or Edge — you can type instead." }); return; }
    const r = new SpeechRecognition();
    r.lang = "en-US"; r.interimResults = true;
    setListening(true);
    r.onresult = (e: any) => {
      const t = Array.from(e.results as ArrayLike<any>).map((x: any) => x[0].transcript).join("");
      onText(t);
      if (e.results[e.results.length - 1].isFinal) onFinal(t);
    };
    r.onerror = (e: any) => notifications.show({ message: `Voice: ${e.error}` });
    r.onend = () => setListening(false);
    r.start();
  };
  return { listening, listen };
}

/** Body of an assistant answer: text, bullets, quoted draft and action buttons. */
export function AnswerBody({ m, onAction }: { m: JarvisMessage; onAction: (a: JarvisAction) => void }) {
  return (
    <>
      <Text size="sm"><Rich text={m.text} /></Text>
      {!!m.bullets?.length && <Box component="ul" my={4} pl="md">{m.bullets.map((b, j) => <li key={j}><Text size="sm"><Rich text={b} /></Text></li>)}</Box>}
      {m.quote && <Paper p="xs" mt={6} withBorder><Text size="sm" className="pre-wrap">{m.quote}</Text></Paper>}
      {!!m.actions?.length && <Group gap={6} mt={8}>{m.actions.map((a, j) => (
        <Button key={j} size="compact-xs" variant={a.kind === "approve" ? "filled" : "default"} onClick={() => onAction(a)}>{a.label}</Button>))}</Group>}
    </>
  );
}
