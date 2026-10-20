import { describe, expect, it } from "vitest";
import { date, dt, impactWord, intensity, isRain, isTornado, pct, scale, scenario, setTimeZone } from "./format";

const tornado = { kind: "Tornado", category: 4, max_wind_mph: 175 };
const hurricane = { kind: "Hurricane", category: 3, max_wind_mph: 120 };
const rain = { kind: "Rain Event", category: 1, max_wind_mph: 30, rain_total_in: 6.5, rain_rate_in_hr: 1.8 };

describe("hazard vocabulary", () => {
  it("names the intensity scale per hazard", () => {
    expect(scale(tornado, 4)).toBe("EF4");
    expect(scale(hurricane, 3)).toBe("Cat 3");
    expect(intensity(tornado)).toBe("EF4 · 175 mph");
    expect(intensity(rain)).toBe("6.5 in rain · 1.8 in/hr peak");
  });
  it("names the impact moment per hazard", () => {
    expect(impactWord(tornado)).toBe("touchdown");
    expect(impactWord(hurricane)).toBe("landfall");
    expect(impactWord(rain)).toBe("rain onset");
    expect(isTornado(tornado) && !isTornado(rain) && isRain(rain)).toBe(true);
  });
  it("labels a prediction run without a scenario name", () => {
    expect(scenario({ category: 2, kind: "tornado" })).toBe("EF2");
    expect(scenario({ category: 2 })).toBe("Cat 2");
    expect(scenario({ category: 2, scenario: "Parent forecast" })).toBe("Parent forecast");
  });
});

describe("formatting", () => {
  it("shows times in the territory's time zone", () => {
    setTimeZone("America/Chicago");
    expect(dt("2026-10-20T02:00:00Z")).toBe("Mon Oct 19, 9:00 PM");
    setTimeZone("America/New_York");
    expect(dt("2026-10-20T02:00:00Z")).toBe("Mon Oct 19, 10:00 PM");
  });
  it("shows date-only values on their own day in every time zone", () => {
    setTimeZone("America/Chicago");
    expect(date("2026-10-20")).toBe("Oct 20, 2026");
    expect(date("2026-10-20T03:00:00Z")).toBe("Oct 19, 2026");  // a moment in time is converted
  });
  it("formats percentages and handles missing values", () => {
    expect(pct(0.1234, 1)).toBe("12.3%");
    expect(pct(null)).toBe("—");
    expect(dt(null)).toBe("—");
  });
});
