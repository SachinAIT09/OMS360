export type Role = "executive" | "ops_manager" | "dispatcher" | "comms" | "admin";
export type EventStatus = "monitoring" | "preparing" | "active" | "restoring" | "closed";
export type OutageStatus = "reported" | "assessed" | "assigned" | "in_progress" | "restored" | "cancelled";

export interface User { id: number; email: string; name: string; title: string; role: Role; role_label: string; active: boolean; last_login_at: string | null; permissions: string[] }

export const EVENT_KINDS = ["Hurricane", "Tropical Storm", "Tropical Depression", "Tornado", "Severe Thunderstorm", "Winter Storm", "Rain Event"] as const;

/** A storm track point; tornado tracks are one or more damage paths (path index, EF rating and damage width on each point). */
export interface TrackPoint { lat: number; lng: number; at: string; observed: boolean; path?: number; ef?: number; width_m?: number }
export interface StormEvent {
  id: number; name: string; kind: string; hazard?: "wind" | "rain" | "tornado"; source: "manual" | "nhc" | "nws"; nhc_id: string | null; status: EventStatus; category: number;
  max_wind_mph: number; pressure_mb: number; lat: number; lng: number; movement: string; landfall_at: string | null; track: TrackPoint[] | null;
  notes: string; created_at: string; activated_at: string | null; restoring_at: string | null; closed_at: string | null;
  /** Rain events only (kind "Rain Event"); landfall_at is then the rain onset. */
  rain_total_in: number | null; rain_rate_in_hr: number | null; duration_h: number | null; soil_saturation: number | null;
  predicted?: number | null; tickets?: number; customers_affected?: number;
}

export interface Hazard { gust_mph?: number; rain_in?: number; surge_ft?: number; arrival_at?: string; path_km?: number | null }
export interface PredZone {
  id: string; name: string; short: string; customers: number; pred: number; pct: number; eta_h: number; driver: string; hazard?: Hazard | null;
  circuits_in_path?: number;
}
export interface PredCircuit {
  id: string; zone_id: string; zone: string; substation: string | null; region_id: string | null; region: string | null; customers: number; pred: number;
  pct: number; eta_h: number; low_h: number; high_h: number; confidence: number; overhead_pct: number; years_since_trim: number;
  /** Transformer health on the circuit (absent on runs made before the asset register existed). */
  asset_hi?: number; pct_poor?: number; mean_xfmr_age?: number; xfmrs?: number;
  /** Tornadoes: closest approach to a damage path, how directly it is hit (0–1) and whether it is rebuilt rather than repaired. */
  in_path?: boolean; path_km?: number | null; core?: number; path_ef?: number | null; rebuild_out?: number;
}
export interface PredRegion {
  id: string | null; name: string; pred: number; circuits: number; line_workers: number; tree_workers: number; eta_h: number; low_h: number; high_h: number;
  last_h: number; last_high_h: number; confidence: number; circuits_in_path?: number; xfmrs_in_path?: number;
}
export interface TornadoPath { ef: number; width_m: number; length_km: number; circuits_hit: number; customers_in_path: number; xfmrs_in_path: number; start_at: string | null }
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
  kind?: "wind" | "rain" | "tornado"; scenario?: string; rain_in?: number | null; forecast?: { id: number; source: string; issued_at: string } | null;
  circuits?: PredCircuit[]; regions?: PredRegion[];
  ef?: number; paths?: TornadoPath[]; circuits_in_path?: number; customers_in_path?: number;
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
  /** Mean transformer health on the circuit and its Poor/Critical share (null without an asset register). */
  asset_hi?: number | null; pct_poor?: number | null;
}
export interface RegionEtr {
  id: string; name: string; zones: string[]; customers_out: number; open_tickets: number; circuits_out: number; etr_at: string | null;
  confidence: number | null; circuits_published: number; circuits_ready: number; crews: number; waiting: number; backlog_h: number;
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
  heading_deg: number; speed_mph: number; movement: string; updated_at: string; distance_mi: number; advisory_url: string;
}

// ---------------------------------------------------------------- asset age and health
export type Condition = "Good" | "Fair" | "Poor" | "Critical";
export interface AssetRollup {
  xfmrs: number; mean_age: number; oldest: number; mean_hi: number; poor: number; critical: number; pct_poor: number; pct_over_life: number;
  expected_failures: number; risk: number; replacement_capex: number;
}
export interface RegionHealth extends AssetRollup {
  id: string; name: string; circuits: number; power_transformers: number; power_poor: number; power_mean_age: number;
}
export interface CircuitHealth extends AssetRollup {
  id: string; zone_id: string; zone: string; region_id: string | null; region: string | null; substation_id: string | null; substation: string | null;
  customers: number; overhead_pct: number | null; critical_facility: string | null;
}
export interface Asset {
  id: string; kind: "power_transformer" | "dist_transformer"; name: string; substation_id: string | null; feeder_id: string | null; zone_id: string;
  lat: number; lng: number; install_year: number; age: number; manufacturer: string; rating_kva: number; mounting: string; phases: number;
  last_inspection: number | null; inspection_score: number | null; peak_load_pct: number | null; dga_tdcg_ppm: number | null;
  oil_moisture_ppm: number | null; through_faults: number | null; ltc: boolean; maintenance_overdue: boolean;
  health_index: number; condition: Condition; pof_12m: number; risk_score: number; replacement_cost: number; drivers: string[];
}
export interface SubstationAsset extends Asset { substation: string; region_id: string | null; region: string | null; zone: string | null; circuits: number }
export interface AssetSummary {
  distribution: AssetRollup; power: AssetRollup; bands: Record<Condition, number>; power_bands: Record<Condition, number>;
  age_histogram: { decade: string; count: number }[]; regions: RegionHealth[]; replacement_capex: number; density: number; top_risk: Asset[];
}
export interface CircuitHealthDetail extends CircuitHealth {
  route: [number, number][][] | null; bands: Record<Condition, number>; age_histogram: { decade: string; count: number }[];
  hi_histogram: { band: string; count: number }[]; transformers: Asset[]; offset: number; limit: number; power_transformers: Asset[];
}

export interface PlanOutlook { pct_poor: number; poor: number; expected_failures: number; risk: number }
export interface ReplacementPlan {
  budget: number; region: string | null; kind: string | null; units: number; cost: number; fleet: number; poor_replaced: number;
  by_kind: Record<string, number>; risk_reduced_pct: number; failures_avoided: number;
  projection: { year: number; label: string; no_action: PlanOutlook; with_plan: PlanOutlook }[];
  frontier: { budget: number; risk_reduced_pct: number }[];
  by_region: { id: string; name: string; units: number; power: number; cost: number; risk_reduced: number }[];
  items: { id: string; kind: string; name: string; where: string | null; region: string | null; age: number; health_index: number;
    condition: Condition; cost: number; risk_reduced: number; drivers: string[] }[];
}
export interface NwsAlert {
  id: string; event: string; headline: string; area: string; severity: string; onset: string | null; expires: string | null;
  ef_estimate: number | null; detection: string; damage_threat: string; max_hail: string; lat: number | null; lng: number | null;
  motion: { lat: number; lng: number; heading_deg: number; speed_mph: number } | null; polygon: [number, number][]; importable: boolean;
}
