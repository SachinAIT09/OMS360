import { describe, expect, it } from "vitest";
import { corridor, metres, trackSpan } from "./geo";

describe("corridor", () => {
  it("is as wide as the damage path, centred on the segment", () => {
    const a: [number, number] = [35.33, -97.49], b: [number, number] = [35.39, -97.42];
    const [p1, , , p4] = corridor(a, b, 650);
    expect(metres(p1, p4)).toBeGreaterThan(1290);
    expect(metres(p1, p4)).toBeLessThan(1310);
    expect(metres(p1, a)).toBeCloseTo(metres(p4, a), 0);
  });
  it("handles a zero-length segment without NaN", () => {
    const c = corridor([35, -97], [35, -97], 100);
    expect(c.flat().every(Number.isFinite)).toBe(true);
  });
});

describe("metres", () => {
  it("measures a degree of latitude as ~110.6 km", () => {
    expect(metres([35, -97], [36, -97])).toBeGreaterThan(110_000);
    expect(metres([35, -97], [36, -97])).toBeLessThan(111_000);
  });
});

describe("trackSpan", () => {
  it("returns the first and last time on a track", () => {
    expect(trackSpan([{ at: "2026-10-20T02:00:00Z" }, { at: "2026-10-20T01:00:00Z" }, { at: "2026-10-20T06:30:00Z" }]))
      .toEqual([Date.parse("2026-10-20T01:00:00Z"), Date.parse("2026-10-20T06:30:00Z")]);
  });
  it("is null for empty or invalid tracks", () => {
    expect(trackSpan([])).toBeNull();
    expect(trackSpan(null)).toBeNull();
    expect(trackSpan([{ at: "not a date" }])).toBeNull();
  });
});
