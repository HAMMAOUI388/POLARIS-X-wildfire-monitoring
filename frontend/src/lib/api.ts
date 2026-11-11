export type ApiError = Error & { status?: number; code?: string };
export type User = { id: string; email: string; display_name: string; roles: string[] };
export type TokenPair = { access_token: string; refresh_token: string; user: User };
export type Location = { id: string; owner_id: string; name: string; location_type: string; description: string | null; point: { longitude: number; latitude: number } };
export type Observation = { id: string; external_id: string; product: string; observed_at: string; confidence: string | null; frp: string | null; brightness_temperature: string | null; point: { longitude: number; latitude: number }; distance_m: number };
export type DetectionEvent = { id: string; status: string; started_at: string; ended_at: string | null; observation_count: number | null };
export type Alert = { id: string; location_id: string | null; event_id: string | null; alert_type: string; classification: string; severity: string; status: "read" | "unread"; read_at: string | null; title: string; message: string; created_at: string; expires_at: string | null; match: { subscription_id: string | null; observation_id: string | null; event_id: string | null; distance_m: string | null; policy: Record<string, unknown> }; evidence: { type: string; id: string; details: Record<string, unknown> }[] };
export type ChatMessage = { id: string; role: string; content: string; created_at: string; tool_summaries: { tool?: string; status?: string; provider?: string }[] };
export type Conversation = { id: string; started_at: string; archived_at: string | null; messages?: ChatMessage[] };
export type PlaceSearchResult = { provider_id: string; display_name: string; point: { longitude: number; latitude: number }; category: string; type: string };
export type MonitoringSubscription = { id: string; user_id: string; location_id: string | null; location_name?: string | null; route_id: string | null; radius_m: number; minimum_severity: "low" | "moderate" | "high" | "critical"; enabled: boolean };
export type RegionalEvent = { id: string; status: string; started_at: string; ended_at: string | null; centroid: { longitude: number; latitude: number } | null };
export type OperationalSummary = { status: string; active_events_count: number; total_observations_count: number; mode: string };
export type SystemOverview = { status: string; total_users: number; roles: Record<string, number>; data_sources: { id: string; name: string; provider: string; type: string }[] };
export type RoutePoint = { longitude: number; latitude: number };
export type RoutePreviewInput = { origin: RoutePoint; destination: RoutePoint; waypoints?: RoutePoint[]; profile?: string };
export type RoutePreviewResult = { provider: string; profile: string; distance_m: number; duration_s: number; geometry: { type: string; coordinates: [number, number][] } | Record<string, unknown>; waypoints: RoutePoint[]; saved: boolean; message: string };

export type IoTNode = {
  id: string;
  node_identifier: string;
  name: string;
  status: string;
  active?: boolean;
  dev_eui: string | null;
  location_id?: string | null;
  battery_voltage: number | null;
  last_seen_at: string | null;
  last_f_cnt?: number | null;
  location?: {
    id: string;
    name: string;
    coordinates: { longitude: number; latitude: number } | null;
  } | null;
};

export type IoTTelemetryMeasurement = {
  sensor_id: string;
  sensor_kind: string | null;
  sensor_identifier: string | null;
  value_numeric: number | null;
  raw_value_numeric: number | null;
  unit: string | null;
  raw_value_unit: string | null;
  quality_flag: string | null;
  measured_at: string | null;
  received_at: string;
};

export type IoTLatestTelemetry = {
  node_id: string;
  node_identifier: string;
  name: string;
  status: string;
  active: boolean;
  dev_eui: string | null;
  battery_voltage: number | null;
  last_seen_at: string | null;
  last_f_cnt: number | null;
  latest_uplink: {
    id: string | null;
    session_id: string | null;
    f_cnt: number | null;
    lns_received_at: string | null;
    rssi_dbm: number | null;
    snr_db: number | null;
    gateway_count: number;
    location_snapshot: {
      name: string | null;
      point: { longitude: number; latitude: number } | null;
    } | null;
  } | null;
  measurements: IoTTelemetryMeasurement[];
};

export type IoTHistoryMeasurement = {
  sensor_identifier: string | null;
  kind: string | null;
  value: number | null;
  unit: string | null;
  quality_flag: string | null;
};

export type IoTHistoryItem = {
  uplink_id: string;
  f_cnt: number;
  lns_received_at: string;
  rssi_dbm: number | null;
  snr_db: number | null;
  location_name: string | null;
  location_point: { longitude: number; latitude: number } | null;
  measurements: IoTHistoryMeasurement[];
};

export type PortalTarget = "professional" | "public" | "denied";

export type RoleEvaluation = {
  portal: PortalTarget;
  isAdmin: boolean;
  isAuthority: boolean;
  isFarmOwner: boolean;
  isUser: boolean;
  canSwitchToPublic: boolean;
  hasRecognizedRole: boolean;
  primaryRoleLabel: string;
};

export function evaluateRoles(roles: string[] | undefined | null): RoleEvaluation {
  if (!roles || !Array.isArray(roles) || roles.length === 0) {
    return {
      portal: "denied",
      isAdmin: false,
      isAuthority: false,
      isFarmOwner: false,
      isUser: false,
      canSwitchToPublic: false,
      hasRecognizedRole: false,
      primaryRoleLabel: "No roles assigned",
    };
  }
  const roleSet = new Set(roles);
  const isAdmin = roleSet.has("admin");
  const isAuthority = roleSet.has("authority");
  const isFarmOwner = roleSet.has("farm_owner");
  const isUser = roleSet.has("user");

  const hasRecognizedRole = isAdmin || isAuthority || isFarmOwner || isUser;
  if (!hasRecognizedRole) {
    return {
      portal: "denied",
      isAdmin: false,
      isAuthority: false,
      isFarmOwner: false,
      isUser: false,
      canSwitchToPublic: false,
      hasRecognizedRole: false,
      primaryRoleLabel: roles.join(", "),
    };
  }

  if (isAdmin) {
    return {
      portal: "professional",
      isAdmin: true,
      isAuthority,
      isFarmOwner,
      isUser,
      canSwitchToPublic: true,
      hasRecognizedRole: true,
      primaryRoleLabel: "System Administrator",
    };
  }

  if (isAuthority) {
    return {
      portal: "professional",
      isAdmin: false,
      isAuthority: true,
      isFarmOwner,
      isUser,
      canSwitchToPublic: false,
      hasRecognizedRole: true,
      primaryRoleLabel: "Regional Authority",
    };
  }

  if (isFarmOwner) {
    return {
      portal: "public",
      isAdmin: false,
      isAuthority: false,
      isFarmOwner: true,
      isUser,
      canSwitchToPublic: false,
      hasRecognizedRole: true,
      primaryRoleLabel: "Farm Owner",
    };
  }

  return {
    portal: "public",
    isAdmin: false,
    isAuthority: false,
    isFarmOwner: false,
    isUser: true,
    canSwitchToPublic: false,
    hasRecognizedRole: true,
    primaryRoleLabel: "Standard User",
  };
}


type ApiOptions = { fetcher?: typeof fetch; onUnauthorized?: () => void; onTokensUpdated?: (accessToken: string) => void };

export class PolarisApi {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private fetcher: typeof fetch;
  private onUnauthorized?: () => void;
  private onTokensUpdated?: (accessToken: string) => void;
  readonly baseUrl: string;

  constructor(baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:5000/api/v1", options: ApiOptions = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetcher = options.fetcher || fetch;
    this.onUnauthorized = options.onUnauthorized;
    this.onTokensUpdated = options.onTokensUpdated;
  }

  setTokens(accessToken: string | null, refreshToken: string | null) { this.accessToken = accessToken; this.refreshToken = refreshToken; }
  getAccessToken() { return this.accessToken; }
  getRefreshToken() { return this.refreshToken; }

  private async send<T>(path: string, init: RequestInit = {}, authorized = true, retry = true): Promise<T> {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (authorized && this.accessToken) headers.set("Authorization", `Bearer ${this.accessToken}`);
    let response: Response;
    try { response = await this.fetcher(`${this.baseUrl}${path}`, { ...init, headers }); }
    catch { throw Object.assign(new Error("Could not reach the POLARIS X server."), { code: "network_error" }) as ApiError; }
    if (response.status === 401 && authorized && retry && this.refreshToken) {
      try {
        const refreshResponse = await this.fetcher(`${this.baseUrl}/auth/refresh`, { method: "POST", headers: { Authorization: `Bearer ${this.refreshToken}` } });
        if (refreshResponse.ok) {
          const result = await refreshResponse.json() as { access_token: string };
          this.accessToken = result.access_token;
          this.onTokensUpdated?.(result.access_token);
          return this.send<T>(path, init, authorized, false);
        }
      } catch { /* the original unauthorized response controls the API error */ }
    }
    if (!response.ok) {
      let body: { error?: { code?: string; message?: string } } = {};
      try { body = await response.json(); } catch { /* response may be empty */ }
      if (response.status === 401 && authorized) this.onUnauthorized?.();
      throw Object.assign(new Error(body.error?.message || `Request failed (${response.status}).`), { status: response.status, code: body.error?.code || "request_error" }) as ApiError;
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  login(email: string, password: string) { return this.send<TokenPair>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false); }
  register(email: string, password: string, display_name: string) { return this.send<{ user: User }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password, display_name }) }, false); }
  me() { return this.send<{ user: User }>("/auth/me"); }
  refresh() { return this.send<{ access_token: string }>("/auth/refresh", { method: "POST" }, false); }
  locations() { return this.send<{ locations: Location[] }>("/locations"); }
  createLocation(input: { name: string; location_type: string; longitude: number; latitude: number; description?: string }) { return this.send<{ location: Location }>("/locations", { method: "POST", body: JSON.stringify(input) }); }
  updateLocation(id: string, input: { name: string; location_type: string; longitude: number; latitude: number; description?: string }) { return this.send<{ location: Location }>(`/locations/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(input) }); }
  deleteLocation(id: string) { return this.send<void>(`/locations/${encodeURIComponent(id)}`, { method: "DELETE" }); }
  subscriptions() { return this.send<{ subscriptions: MonitoringSubscription[] }>("/subscriptions"); }
  subscription(id: string) { return this.send<{ subscription: MonitoringSubscription }>(`/subscriptions/${encodeURIComponent(id)}`); }
  createSubscription(input: { location_id: string; radius_m?: number; minimum_severity?: string; enabled?: boolean }) { return this.send<{ subscription: MonitoringSubscription }>("/subscriptions", { method: "POST", body: JSON.stringify(input) }); }
  updateSubscription(id: string, input: { radius_m?: number; minimum_severity?: string; enabled?: boolean }) { return this.send<{ subscription: MonitoringSubscription }>(`/subscriptions/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(input) }); }
  deleteSubscription(id: string) { return this.send<void>(`/subscriptions/${encodeURIComponent(id)}`, { method: "DELETE" }); }

  observations(locationId: string, radius_m = 5000) { return this.send<{ observations: Observation[]; page: number; limit: number; returned: number; radius_m: number }>(`/geospatial/locations/${encodeURIComponent(locationId)}/observations?radius_m=${radius_m}&page=1&limit=100`); }
  events(locationId: string, radius_m = 5000) { return this.send<{ events: DetectionEvent[]; page: number; limit: number; radius_m: number }>(`/geospatial/locations/${encodeURIComponent(locationId)}/events?radius_m=${radius_m}&page=1&limit=100`); }
  searchPlaces(q: string, limit = 5) { return this.send<{ provider: string; attribution: string; results: PlaceSearchResult[] }>(`/geography/search?q=${encodeURIComponent(q)}&limit=${limit}&countrycodes=ma`); }
  alerts(page = 1, perPage = 100, unread = false) { return this.send<{ alerts: Alert[]; total: number; page: number; per_page: number }>(`/alerts?page=${page}&per_page=${perPage}&unread_only=${unread}`); }
  alert(id: string) { return this.send<{ alert: Alert }>(`/alerts/${encodeURIComponent(id)}`); }
  markAlertRead(id: string) { return this.send<{ alert: Alert }>(`/alerts/${encodeURIComponent(id)}/read`, { method: "POST" }); }
  locationSummary(id: string) { return this.send<{ location_id: string; total_alerts: number; unread_alerts: number; recent_observations_count: number; associated_events_count: number; note: string }>(`/alerts/locations/${encodeURIComponent(id)}/summary`); }
  eventDetails(id: string) { return this.send<{ event: { id: string; status: string; started_at: string; ended_at: string | null; centroid: { longitude: number; latitude: number }; classification: string } }>(`/alerts/events/${encodeURIComponent(id)}`); }
  conversations(page = 1) { return this.send<{ conversations: Conversation[]; total: number; page: number; per_page: number }>(`/chat/conversations?page=${page}&per_page=50`); }
  conversation(id: string) { return this.send<{ conversation: Conversation }>(`/chat/conversations/${encodeURIComponent(id)}`); }
  createConversation() { return this.send<{ conversation: Conversation }>("/chat/conversations", { method: "POST", body: JSON.stringify({}) }); }
  sendMessage(id: string, content: string) { return this.send<{ conversation_id: string; user_message_id: string; assistant_message_id: string; response_text: string; tool_summaries: ChatMessage["tool_summaries"] }>(`/chat/conversations/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify({ content }) }); }
  archiveConversation(id: string) { return this.send<void>(`/chat/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }); }

  authoritySummary() { return this.send<OperationalSummary>("/authority/operational-summary"); }
  authorityEvents() { return this.send<{ events: RegionalEvent[]; count: number }>("/authority/events"); }
  adminSystem() { return this.send<SystemOverview>("/admin/system"); }
  adminIoTNodes() { return this.send<{ nodes: IoTNode[]; count: number }>("/admin/iot/nodes"); }
  authorityIoTNodes() { return this.send<{ nodes: IoTNode[]; count: number }>("/authority/iot/nodes"); }
  iotNodeLatestTelemetry(nodeId: string) { return this.send<IoTLatestTelemetry>(`/iot/nodes/${encodeURIComponent(nodeId)}/telemetry/latest`); }
  iotNodeTelemetryHistory(nodeId: string, limit = 50) { return this.send<{ history: IoTHistoryItem[]; count: number }>(`/iot/nodes/${encodeURIComponent(nodeId)}/telemetry/history?limit=${limit}`); }
  previewRoute(input: RoutePreviewInput) {
    return this.send<RoutePreviewResult>("/geography/routes/preview", {
      method: "POST",
      body: JSON.stringify({
        origin: input.origin,
        destination: input.destination,
        waypoints: input.waypoints || [],
        profile: input.profile || "foot",
      }),
    });
  }
}
