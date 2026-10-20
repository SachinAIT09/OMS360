/* The territory this deployment runs (GET /api/profile): utility name, map view, local time zone and hazard vocabulary.
   Loaded once before the app renders, so every screen can read it synchronously. */
import { API_BASE } from "../api/client";
import { setTimeZone } from "./format";

export interface Profile {
  territory: string; utility: string; utility_short: string; site: string; area: string; state: string; timezone: string;
  hazard: "hurricane" | "tornado"; map_center: [number, number]; map_zoom: number; weather_label: string; has_water: boolean;
  regions: { id: string; name: string }[]; event_kinds: string[]; new_event: { kind: string; lat: number; lng: number };
  sample_addresses: string[]; jarvis_suggestions: string[]; demo_login_domain: string;
}

// Neutral fallback if the API can't be reached at startup (the login page then shows its own connection error).
export let PROFILE: Profile = {
  territory: "", utility: "OMS360 Utility", utility_short: "OMS360", site: "", area: "our service area", state: "", timezone: "America/Chicago",
  hazard: "tornado", map_center: [35.5, -97.5], map_zoom: 7, weather_label: "", has_water: false, regions: [],
  event_kinds: ["Hurricane", "Tropical Storm", "Tropical Depression", "Tornado", "Severe Thunderstorm", "Winter Storm", "Rain Event"],
  new_event: { kind: "Tornado", lat: 35.3, lng: -97.5 }, sample_addresses: [], jarvis_suggestions: [], demo_login_domain: "",
};

export async function loadProfile(): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/profile`);
    if (res.ok) PROFILE = await res.json();
  } catch { /* server unreachable: keep the fallback */ }
  setTimeZone(PROFILE.timezone);
  document.title = `OMS360 · ${PROFILE.utility}`;
}
