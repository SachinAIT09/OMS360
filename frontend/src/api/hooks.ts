import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { api } from "./client";
import type { Reference, RoutesInfo, StormEvent } from "./types";

/** GET helper — the query key is the path so live updates can invalidate by prefix. */
export function useGet<T>(path: string | null, opts: { refetchInterval?: number; enabled?: boolean } = {}) {
  return useQuery<T>({
    queryKey: [path],
    queryFn: () => api.get<T>(path!),
    enabled: !!path && opts.enabled !== false,
    refetchInterval: opts.refetchInterval,
    staleTime: 5_000,
  });
}

/** Mutation with toast + cache invalidation. `invalidate` = path prefixes to refetch. */
export function useAction<V = void, R = unknown>(fn: (v: V) => Promise<R>, opts: { success?: string | ((r: R) => string); invalidate?: string[] } = {}) {
  const qc = useQueryClient();
  return useMutation<R, Error, V>({
    mutationFn: fn,
    onSuccess: r => {
      if (opts.success) notifications.show({ color: "teal", message: typeof opts.success === "function" ? opts.success(r) : opts.success });
      invalidate(qc, opts.invalidate ?? [""]);
    },
    onError: e => notifications.show({ color: "red", title: "Couldn't complete that", message: e.message }),
  });
}

export function invalidate(qc: ReturnType<typeof useQueryClient>, prefixes: string[]) {
  qc.invalidateQueries({
    predicate: q => {
      const k = (q.queryKey as QueryKey)[0];
      return typeof k === "string" && prefixes.some(p => k.startsWith(p));
    },
  });
}

export const useReference = () => useQuery<Reference>({ queryKey: ["/reference"], queryFn: () => api.get("/reference"), staleTime: Infinity });
export const useEvents = () => useGet<StormEvent[]>("/events");
/** Circuit routes for maps (sandbox-drawn until the utility's GIS export is imported). */
export const useRoutes = () => useQuery<RoutesInfo>({ queryKey: ["/network/routes"], queryFn: () => api.get("/network/routes"), staleTime: 10 * 60_000 });
