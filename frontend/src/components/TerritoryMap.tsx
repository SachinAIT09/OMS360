import { useState, type ReactNode } from "react";
import L from "leaflet";
import { Circle, CircleMarker, MapContainer, Marker, Polygon, Polyline, Popup, TileLayer, Tooltip } from "react-leaflet";
import { useComputedColorScheme } from "@mantine/core";
import { API_BASE } from "../api/client";
import type { Facility, TrackPoint, Yard } from "../api/types";
import { dt, FAC_COLOR, fmt, pct, sevColor } from "../lib/format";
import { PROFILE } from "../lib/profile";

export interface MapZone { id: string; short: string; lat: number; lng: number; customers: number; value: number; popup?: ReactNode; restored?: boolean }
export interface MapPin { id: number | string; lat: number; lng: number; color: string; popup?: ReactNode; onClick?: () => void }
/** A circuit route: one or more polylines of [lat, lng]. */
export interface MapLine { id: string; lines: [number, number][][]; color: string; weight?: number; opacity?: number; popup?: ReactNode }

const facIcon = (k: string) => L.divIcon({ className: "", html: `<div class="mk" style="background:${FAC_COLOR[k]}">${k}</div>`, iconSize: [18, 18], iconAnchor: [9, 9] });
const yardIcon = L.divIcon({ className: "", html: `<div class="mk round" style="background:#2b6bff">Y</div>`, iconSize: [18, 18], iconAnchor: [9, 9] });
const stormIcon = L.divIcon({ className: "", html: '<div class="hurr">🌀</div>', iconSize: [28, 28], iconAnchor: [14, 14] });
const tornadoIcon = L.divIcon({ className: "", html: '<div class="twister">🌪️</div>', iconSize: [28, 28], iconAnchor: [14, 14] });
/** Enhanced Fujita colour scale for damage paths. */
export const EF_COLOR = ["#8fd16a", "#f5d33b", "#f5a623", "#f07a2e", "#e0506a", "#b04fd8"];
const pinIcon = (c: string) => L.divIcon({ className: "", html: `<div class="pin" style="background:${c}"></div>`, iconSize: [12, 12], iconAnchor: [6, 6] });

/** Esri canvas basemaps (no API key) with an OpenStreetMap fallback; follows the colour scheme. */
function Basemap({ light }: { light: boolean }) {
  const [failed, setFailed] = useState(0);
  const tone = light ? "Light" : "Dark";
  const esri = (s: string) => `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${tone}_Gray_${s}/MapServer/tile/{z}/{y}/{x}`;
  if (failed >= 6) return <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap" className={light ? "" : "osm-dark"} />;
  return <>
    <TileLayer key={tone} url={esri("Base")} maxZoom={16} attribution="Esri, HERE, Garmin, © OpenStreetMap" eventHandlers={{ tileerror: () => setFailed(f => f + 1) }} />
    <TileLayer key={tone + "r"} url={esri("Reference")} maxZoom={16} opacity={0.8} />
  </>;
}

export function TerritoryMap({ zones = [], pins = [], lines = [], facilities, yards, track, center = PROFILE.map_center, zoom = PROFILE.map_zoom, height = 420, labels = true, light, radarLayer }: {
  zones?: MapZone[]; pins?: MapPin[]; lines?: MapLine[]; facilities?: Facility[]; yards?: Yard[]; track?: TrackPoint[] | null; center?: [number, number]; zoom?: number;
  height?: number | string; labels?: boolean; light?: boolean; radarLayer?: string | null;
}) {
  const scheme = useComputedColorScheme("dark");
  const isLight = light ?? scheme === "light";
  return (
    <MapContainer center={center} zoom={zoom} scrollWheelZoom={false} style={{ height, width: "100%" }}>
      <Basemap light={isLight} />
      {radarLayer && <TileLayer url={`${API_BASE}/weather/tiles/${radarLayer}/{z}/{x}/{y}.png`} opacity={0.7} attribution="Weather © OpenWeather" />}
      {zones.map(z => {
        const col = z.restored ? "#3ec46d" : sevColor(z.value);
        return (
          <Circle key={z.id} center={[z.lat, z.lng]} radius={Math.sqrt(z.customers) * 15} pathOptions={{ color: col, weight: 1.5, fillColor: col, fillOpacity: 0.3 }}>
            {z.popup && <Popup>{z.popup}</Popup>}
            {labels && <Tooltip permanent direction="center" className="zlabel">{z.short}</Tooltip>}
          </Circle>
        );
      })}
      {lines.map(l => (
        <Polyline key={l.id} positions={l.lines} pathOptions={{ color: l.color, weight: l.weight ?? 3, opacity: l.opacity ?? 0.9 }}>
          {l.popup && <Popup>{l.popup}</Popup>}
        </Polyline>))}
      {track && track.length > 1 && (track.some(p => p.path != null) ? <TornadoPaths track={track} /> : <StormTrack track={track} />)}
      {facilities?.map(f => (
        <Marker key={f.id} position={[f.lat, f.lng]} icon={facIcon(f.kind)}>
          <Popup><b>{f.name}</b><br />{f.type} · feeder {f.feeder_id}<br />Backup: {f.backup}</Popup>
        </Marker>))}
      {yards?.map(y => (
        <Marker key={y.id} position={[y.lat, y.lng]} icon={yardIcon}>
          <Popup><b>{y.name}</b><br />Capacity {fmt(y.capacity)} workers{y.staged_workers != null && <><br />{fmt(y.staged_workers)} staged</>}<br />{y.active ? "Open" : "Closed"}</Popup>
        </Marker>))}
      {pins.map(p => (
        <Marker key={p.id} position={[p.lat, p.lng]} icon={pinIcon(p.color)} eventHandlers={p.onClick ? { click: p.onClick } : undefined}>
          {p.popup && !p.onClick && <Popup>{p.popup}</Popup>}
        </Marker>))}
    </MapContainer>
  );
}

function StormTrack({ track }: { track: TrackPoint[] }) {
  const now = Date.now();
  const pts = track.map(p => [p.lat, p.lng] as [number, number]);
  let idx = 0;
  track.forEach((p, i) => { if (new Date(p.at).getTime() <= now) idx = i; });
  const future = track.slice(idx + 1);
  return <>
    <Polyline positions={pts.slice(0, idx + 1)} pathOptions={{ color: "#ffffff", weight: 2.5, opacity: 0.85 }} />
    <Polyline positions={pts.slice(idx)} pathOptions={{ color: "#f5a623", weight: 2.5, dashArray: "6 6" }} />
    {future.map((p, i) => <Circle key={`c${i}`} center={[p.lat, p.lng]} radius={30000 + i * 30000} pathOptions={{ stroke: false, fillColor: "#ffffff", fillOpacity: 0.06 }} />)}
    {future.map((p, i) => (
      <CircleMarker key={`f${i}`} center={[p.lat, p.lng]} radius={4} pathOptions={{ color: "#f5a623", fillColor: "#0b1532", fillOpacity: 1, weight: 2 }}>
        <Tooltip>Forecast position · {dt(p.at)}</Tooltip>
      </CircleMarker>))}
    <Marker position={pts[idx]} icon={stormIcon}><Popup>Current position · {dt(track[idx].at)}</Popup></Marker>
  </>;
}

/** Tornado damage paths drawn to scale: a corridor as wide as the damage width, coloured by EF rating, solid where the
    tornado has already passed and dashed ahead of it, with the twister at its current (or touchdown) position. */
function TornadoPaths({ track }: { track: TrackPoint[] }) {
  const now = Date.now();
  const paths = new Map<number, TrackPoint[]>();
  track.forEach(p => paths.set(p.path ?? 0, [...(paths.get(p.path ?? 0) ?? []), p]));
  return <>
    {[...paths.entries()].map(([i, pts]) => {
      const ef = pts[0].ef ?? 0;
      const col = EF_COLOR[Math.max(0, Math.min(5, ef))];
      const half = (pts[0].width_m ?? 400) / 2;
      const ll = pts.map(p => [p.lat, p.lng] as [number, number]);
      const passed = pts.filter(p => new Date(p.at).getTime() <= now).length;
      const here = pts[Math.max(0, passed - 1)];
      return (
        <span key={i}>
          {ll.slice(1).map((b, k) => <Polygon key={k} positions={corridor(ll[k], b, half)} pathOptions={{ stroke: false, fillColor: col, fillOpacity: 0.35 }}>
            <Tooltip sticky>EF{ef} damage path · {fmt(half * 2)} m wide · {dt(pts[k].at)}</Tooltip></Polygon>)}
          {passed > 1 && <Polyline positions={ll.slice(0, passed)} pathOptions={{ color: col, weight: 2.5, opacity: 0.95 }} />}
          {passed < ll.length && <Polyline positions={ll.slice(Math.max(0, passed - 1))} pathOptions={{ color: col, weight: 2, dashArray: "6 6" }} />}
          <Marker position={[here.lat, here.lng]} icon={tornadoIcon}>
            <Popup><b>EF{ef} tornado</b><br />{passed ? "Passed" : "Forecast touchdown"} · {dt(here.at)}<br />Damage width {fmt(half * 2)} m</Popup>
          </Marker>
        </span>
      );
    })}
  </>;
}

/** The four corners of a corridor `half` metres either side of segment a→b. */
function corridor(a: [number, number], b: [number, number], half: number): [number, number][] {
  const kx = 111320 * Math.cos((a[0] * Math.PI) / 180), ky = 110570;
  const dx = (b[1] - a[1]) * kx, dy = (b[0] - a[0]) * ky;
  const len = Math.hypot(dx, dy) || 1;
  const ox = (-dy / len) * half, oy = (dx / len) * half;
  const off = (p: [number, number], s: number): [number, number] => [p[0] + (s * oy) / ky, p[1] + (s * ox) / kx];
  return [off(a, 1), off(b, 1), off(b, -1), off(a, -1)];
}

export function MapLegend({ mode = "out" }: { mode?: "out" | "pred" }) {
  const items: [string, string][] = [["#3ec46d", "< 8%"], ["#f5a623", "8–20%"], ["#f07a2e", "20–40%"], ["#e0506a", "> 40%"]];
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 11, opacity: 0.85, marginTop: 8 }}>
      <span>{mode === "pred" ? "Predicted outage probability" : "Customers out"}:</span>
      {items.map(([c, l]) => <span key={l} style={{ display: "flex", alignItems: "center", gap: 4 }}><i style={{ width: 9, height: 9, borderRadius: 2, background: c, display: "inline-block" }} />{l}</span>)}
      <span>· <b style={{ color: FAC_COLOR.H }}>H</b> hospital <b style={{ color: FAC_COLOR.W }}>W</b> water <b style={{ color: FAC_COLOR.S }}>S</b> shelter · <b style={{ color: "#2b6bff" }}>Y</b> staging yard</span>
    </div>
  );
}

export const zonePopup = (name: string, rows: [string, ReactNode][]) => (
  <div><b>{name}</b>{rows.map(([k, v]) => <div key={k}>{k}: <b>{v}</b></div>)}</div>
);
export { pct, fmt };
