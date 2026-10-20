/* Small geometry helpers for the maps (pure, unit-tested). */

/** The four corners of a corridor `half` metres either side of segment a→b ([lat, lng]). */
export function corridor(a: [number, number], b: [number, number], half: number): [number, number][] {
  const kx = 111320 * Math.cos((a[0] * Math.PI) / 180), ky = 110570;
  const dx = (b[1] - a[1]) * kx, dy = (b[0] - a[0]) * ky;
  const len = Math.hypot(dx, dy) || 1;
  const ox = (-dy / len) * half, oy = (dx / len) * half;
  const off = (p: [number, number], s: number): [number, number] => [p[0] + (s * oy) / ky, p[1] + (s * ox) / kx];
  return [off(a, 1), off(b, 1), off(b, -1), off(a, -1)];
}

/** Distance in metres between two [lat, lng] points (equirectangular; fine at city scale). */
export function metres(a: [number, number], b: [number, number]): number {
  const kx = 111320 * Math.cos((((a[0] + b[0]) / 2) * Math.PI) / 180);
  return Math.hypot((b[1] - a[1]) * kx, (b[0] - a[0]) * 110570);
}

/** All the points of a list of polylines (for zooming to them). */
export const flatten = (lines: [number, number][][][]): [number, number][] => lines.flat(2 as 1) as unknown as [number, number][];

/** The time range a tornado track spans ([first, last] in ms), or null. */
export function trackSpan(track: { at: string }[] | null | undefined): [number, number] | null {
  if (!track?.length) return null;
  const ts = track.map(p => new Date(p.at).getTime()).filter(t => !Number.isNaN(t));
  return ts.length ? [Math.min(...ts), Math.max(...ts)] : null;
}
