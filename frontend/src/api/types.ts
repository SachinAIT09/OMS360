export type Role = "executive" | "ops_manager" | "dispatcher" | "comms" | "admin";
export type EventStatus = "monitoring" | "preparing" | "active" | "restoring" | "closed";
export type OutageStatus = "reported" | "assessed" | "assigned" | "in_progress" | "restored" | "cancelled";

export interface User { id: number; email: string; name: string; title: string; role: Role; role_label: string; active: boolean; last_login_at: string | null; permissions: string[] }

export const EVENT_KINDS = ["Hurricane", "Tropical Storm", "Tropical Depression", "Severe Thunderstorm", "Winter Storm", "Rain Event"] as const;

export interface TrackPoint { lat: number; lng: number; at: string; observed: boolean }
export interface StormEvent {
  id: number; name: string; kind: string; source: "manual" | "nhc"; nhc_id: string | null; status: EventStatus; category: number;
  max_wind_mph: number; pressure_mb: number; lat: number; lng: number; movement: string; landfall_at: string | null; track: TrackPoint[] | null;
  notes: string; created_at: string; activated_at: string | null; restoring_at: string | null; closed_at: string | null;
  /** Rain events only (kind "Rain Event"); landfall_at is then the rain onset. */
  rain_total_in: number | null; rain_rate_in_hr: number | null; duration_h: number | null; soil_saturation: number | null;
  predicted?: number | null; tickets?: number; customers_affected?: number;
}

export interface Hazard { gust_mph?: number; rain_in?: number; surge_ft?: number; arrival_at?: string }
export interface PredZone { id: string; name: string; short: string; customers: number; pred: number; pct: number; eta_h: number; driver: string; hazard?: Hazard | null }
export interface PredCircuit {
  id: string; zone_id: string; zone: string; substation: string | null; region_id: string | null; region: string | null; customers: number; pred: number;
  pct: number; eta_h: number; low_h: number; high_h: number; confidence: number; overhead_pct: number; years_since_trim: number;
}
export interface PredRegion { id: string | null; name: string; pred: number; circuits: number; eta_h: number; low_h: number; high_h: number; last_h: number; last_high_h: number; confidence: number }
export interface ForecastZone extends Hazard { zone_id: string; zone: string; filled?: boolean }
export interface ForecastInfo {
  latest: { id: number; source: string; issued_at: string; created_by: string; created_at: string; zones: ForecastZone[] } | null;
  history: { id: number; source: string; issued_at: string; created_by: string }[]; sample_csv: string;
}
export interface Calibration {
  window_h: number; snapshots: number; simulated_pct: number; gap_pts: number | null;
  bands: { band: string; count: number; promised_pct: number; actual_pct: number; mae_h: number }[];
}
export interface Prediction {
  kind?: "wind" | "rain"; scenario?: string; rain_in?: number | null; forecast?: { id: number; source: string; issued_at: string } | null;
  circuits?: PredCircuit[]; regions?: PredRegion[];
  category: number; wind_mph: number; surge: string | null; pred_total: number; total_customers: number; zones: PredZone[];
  required: Crew3; internal: Crew3; committed: Crew3; needed: Crew3; coverage: number; avg_eta_h: number; p95_eta_h: number; confidence: number;
  critical_at_risk: number; facilities: { id: number; name: string; kind: string; type: string; feeder: string; backup: string; risk: string }[];
  lift_stations_at_risk: number; lift_stations_total: number; generators_needed: number; water_customers_at_risk: number; boil_water_zones: string[];
  feeders: { id: string; zone: string; pred: number }[]; materials: { poles: number; transformers: number; conductor_miles: number };
}
export type Crew3 = { line: number; tree: number; da: number };
export interface PredictionRun { id: number | null; category: number; created_at: string; result: Prediction }

export interface ZoneStat {
  id: string; name: string; short: string; lat: number; lng: number; customers: number; coastal: boolean; critical: boolean; medical: boolean;
  affected: number; customers_out: number; open_tickets: number; crews: number; etr_at: string | null; confidence: number | null;
  published: boolean; published_at: string | null; pct_out: number;
}
export interface EventStats {
  tickets_total: number; tickets_by_status: Record<string, number>; open_tickets: number; unassigned: number; customers_affected: number;
  customers_out: number; restored_pct: number; crews_by_status: Record<string, number>; line_workers_on_hand: number; critical_open: number;
  zones: ZoneStat[]; last_etr_at: string | null; published_zones: number;
}
export interface CircuitEtr {
  id: string; customers: number | null; lat: number; lng: number; substation_id: string | null; substation: string | null; zone_id: string; zone: string;
  region_id: string | null; region: string | null; customers_out: number; open_tickets: number; crews: number; etr_at: string | null;
  confidence: number; published: boolean; published_at: string | null;
}
export interface RegionEtr {
  id: string; name: string; zones: string[]; customers_out: number; open_tickets: number; circuits_out: number; etr_at: string | null;
  confidence: number | null; circuits_published: number; circuits_ready: number;
}
export interface RoutesInfo {
  feeders: { id: string; zone: string | null; substation: string | null; source: "synthetic" | "imported" | null; route: [number, number][][] }[];
  counts: Record<string, number>; substations: { id: string; name: string; lat: number; lng: number }[];
}
export interface NetworkEtrs { regions: RegionEtr[]; circuits: CircuitEtr[]; publish_confidence: number; can_publish: boolean }
export interface Curve { start: string; points: { hour: number; at: string; out: number; restored_pct: number }[] }
export interface Task { id: number; event_id: number | null; title: string; owner_role: string; status: "open" | "done"; due_at: string | null; created_at: string; done_at: string | null }
export interface Audit { id: number; at: string; user: string; action: string; entity: string; entity_id: string; event_id: number | null; detail: string }
export interface Overview { event: StormEvent; prediction: PredictionRun | null; stats: EventStats; curve: Curve | null; tasks: Task[]; activity: Audit[]; pending_messages: number }

export interface Recommendation {
  id: number; event_id: number; key: string; priority: "Critical" | "High" | "Medium"; title: string; detail: string; impact: string; why: string;
  status: "open" | "approved" | "dismissed"; created_at: string; decided_by: string | null; decided_at: string | null; outcome: string;
}

export interface Outage {
  id: number; number: string; event_id: number | null; zone_id: string; zone: string; feeder_id: string; device: string; cause: string; damage: string;
  customers: number; priority: "critical" | "high" | "normal"; facility_id: number | null; status: OutageStatus; source: string; lat: number; lng: number;
  crew: { id: number; code: string; company: string } | null; reported_at: string; assigned_at: string | null; started_at: string | null;
  restored_at: string | null; etr_at: string | null; etr_committed: boolean; etr_override: boolean; notes: string;
  /** How settled this ticket's ETR is (open tickets only). */
  etr_confidence: number | null;
}
export interface OutageDetail extends Outage { facility: string | null; job_hours: number; history: { id: number; at: string; kind: string; text: string; user: string }[]; allowed: OutageStatus[] }
export interface Page<T> { total: number; page: number; size: number; items: T[] }

export interface Crew {
  id: number; code: string; kind: "line" | "tree" | "assessment"; company: string; source: "internal" | "mutual_aid"; size: number;
  status: "available" | "staged" | "assigned" | "working" | "off_shift" | "released"; lead: string; lat: number; lng: number; yard_id: number | null;
  mutual_aid_id: number | null; current: { id: number; number: string; zone: string; status: string } | null;
}
export interface Yard { id: number; name: string; lat: number; lng: number; capacity: number; active: boolean; staged_workers?: number }
export interface MutualAid {
  id: number; event_id: number; company: string; origin: string; kind: string; workers: number; status: string; eta: string | null;
  cost_per_worker_day: number; requested_by: string; requested_at: string; arrived_at: string | null; released_at: string | null;
}

export interface Message {
  id: number; event_id: number | null; channel: string; audience: string; subject: string; body: string;
  status: "draft" | "pending" | "scheduled" | "sent" | "rejected"; ai_generated: boolean; recipients: number; created_by: string;
  approved_by: string | null; reject_reason: string; scheduled_for: string | null; sent_at: string | null; created_at: string; updated_at: string;
}
export interface Audience { id: string; name: string; count: number }
export interface Rule { id: number; name: string; trigger: string; channel: string; enabled: boolean; sent_count: number }

export interface Facility { id: number; name: string; kind: string; type: string; lat: number; lng: number; zone_id: string; feeder_id: string; backup: string }
export interface Zone { id: string; code: string; name: string; short: string; lat: number; lng: number; customers: number; water_customers: number; vulnerability: number; coastal: boolean; critical: boolean; medical: boolean }
export interface Reference {
  zones: Zone[]; facilities: Facility[]; yards: Yard[]; feeders: { id: string; zone_id: string }[]; total_customers: number; total_water: number;
  channels: Record<string, string>; purposes: Record<string, string>;
}

export interface JarvisAction { label: string; kind: "approve" | "nav"; value: string | number }
export interface JarvisMessage { role: "user" | "jarvis"; id?: number; text: string; bullets?: string[]; actions?: JarvisAction[]; say?: string; quote?: string | null; saved?: boolean; conversation_id?: number }
export interface JarvisConversation { id: number; title: string; created_at: string; updated_at: string; questions: number }
export interface JarvisSaved extends JarvisMessage { id: number; conversation_id: number; question: string | null; created_at: string }

export interface Weather {
  source: string; error: string | null; key_error?: string | null; temp_f: number; humidity: number; pressure_mb: number; wind_mph: number; gust_mph: number;
  description: string; updated_at: string; radar_available: boolean; hourly: { time: string; gust_mph: number; rain_chance: number }[];
}
export interface NhcStorm {
  nhc_id: string; name: string; kind: string; lat: number; lng: number; wind_mph: number; category: number; pressure_mb: number;
  heading_deg: number; speed_mph: number; movement: string; updated_at: string; distance_to_tampa_mi: number; advisory_url: string;
}
