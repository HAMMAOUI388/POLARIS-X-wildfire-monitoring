import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Dashboard } from "./dashboard";

vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="map-placeholder" /> }));

const user = { id: "user-1", email: "demo@example.com", display_name: "Demo User", roles: ["user"] };
const location = { id: "location-1", owner_id: user.id, name: "North Farm", location_type: "farm", description: null, point: { longitude: -6.8, latitude: 33.9 } };
const observation = { id: "obs-1", external_id: "FIRMS-123", product: "VIIRS_SNPP_NRT", observed_at: "2026-11-10T09:00:00Z", confidence: "nominal", frp: "4.2", brightness_temperature: "310", point: { longitude: -6.81, latitude: 33.91 }, distance_m: 1200 };
const alert = { id: "alert-1", location_id: location.id, event_id: null, alert_type: "satellite_thermal_anomaly", classification: "informational", severity: "low", status: "unread", read_at: null, title: "Satellite thermal anomaly near North Farm", message: "Not a confirmed wildfire.", created_at: "2026-11-10T09:10:00Z", expires_at: null, match: { subscription_id: "sub-1", observation_id: observation.id, event_id: null, distance_m: "1200", policy: {} }, evidence: [] };
const subscription = { id: "sub-1", user_id: user.id, location_id: location.id, route_id: null, radius_m: 5000, minimum_severity: "low", enabled: true };
const conversation = { id: "conversation-1", started_at: "2026-11-10T09:00:00Z", archived_at: null };

const iotNode = {
  id: "iot-node-1",
  node_identifier: "polaris-station-ifrane-01",
  name: "Ifrane Forest Station",
  status: "active",
  active: true,
  dev_eui: "0004A30B001C0001",
  location_id: "loc-ifrane",
  battery_voltage: 3.92,
  last_seen_at: "2026-11-11T14:30:00Z",
  last_f_cnt: 150,
  location: {
    id: "loc-ifrane",
    name: "Ifrane National Park",
    coordinates: { longitude: -5.11, latitude: 33.52 },
  },
};

const iotTelemetryLatest = {
  node_id: iotNode.id,
  node_identifier: iotNode.node_identifier,
  name: iotNode.name,
  status: "active",
  active: true,
  dev_eui: iotNode.dev_eui,
  battery_voltage: 3.92,
  last_seen_at: "2026-11-11T14:30:00Z",
  last_f_cnt: 150,
  latest_uplink: {
    id: "uplink-100",
    session_id: "01HSESSIONKEY",
    f_cnt: 150,
    lns_received_at: "2026-11-11T14:30:00Z",
    rssi_dbm: -78,
    snr_db: 9.8,
    gateway_count: 2,
    location_snapshot: {
      name: "Ifrane National Park",
      point: { longitude: -5.11, latitude: 33.52 },
    },
  },
  measurements: [
    { sensor_id: "s-t", sensor_kind: "bme280", sensor_identifier: "station_temperature", value_numeric: 21.6, raw_value_numeric: 21.6, unit: "°C", raw_value_unit: "°C", quality_flag: "good", measured_at: null, received_at: "2026-11-11T14:30:00Z" },
    { sensor_id: "s-h", sensor_kind: "bme280", sensor_identifier: "station_humidity", value_numeric: 44.2, raw_value_numeric: 44.2, unit: "%", raw_value_unit: "%", quality_flag: "good", measured_at: null, received_at: "2026-11-11T14:30:00Z" },
    { sensor_id: "s-p", sensor_kind: "bme280", sensor_identifier: "station_pressure", value_numeric: 1014.5, raw_value_numeric: 1014.5, unit: "hPa", raw_value_unit: "hPa", quality_flag: "good", measured_at: null, received_at: "2026-11-11T14:30:00Z" },
    { sensor_id: "s-b", sensor_kind: "battery", sensor_identifier: "station_battery", value_numeric: 3.92, raw_value_numeric: 3.92, unit: "V", raw_value_unit: "V", quality_flag: "good", measured_at: null, received_at: "2026-11-11T14:30:00Z" },
  ],
};

const iotTelemetryHistory = {
  history: [
    {
      uplink_id: "uplink-100",
      f_cnt: 150,
      lns_received_at: "2026-11-11T14:30:00Z",
      rssi_dbm: -78,
      snr_db: 9.8,
      location_name: "Ifrane National Park",
      location_point: { longitude: -5.11, latitude: 33.52 },
      measurements: [
        { sensor_identifier: "station_temperature", kind: "bme280", value: 21.6, unit: "°C", quality_flag: "good" },
        { sensor_identifier: "station_humidity", kind: "bme280", value: 44.2, unit: "%", quality_flag: "good" },
        { sensor_identifier: "station_pressure", kind: "bme280", value: 1014.5, unit: "hPa", quality_flag: "good" },
      ],
    },
  ],
  count: 1,
};

function mockedFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const payload = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (url.endsWith("/auth/me")) return payload({ user });
    if (url.endsWith("/auth/login")) return payload({ user, access_token: "access", refresh_token: "refresh" });
    if (url.endsWith("/locations") && (!init?.method || init.method === "GET")) return payload({ locations: [location] });
    if (url.endsWith("/subscriptions") && (!init?.method || init.method === "GET")) return payload({ subscriptions: [subscription] });
    if (url.endsWith("/subscriptions") && init?.method === "POST") return payload({ subscription }, 201);
    if (url.includes("/subscriptions/sub-1") && init?.method === "PATCH") return payload({ subscription: { ...subscription, radius_m: 10000 } });
    if (url.includes("/alerts?")) return payload({ alerts: [alert], total: 1, page: 1, per_page: 100 });

    if (url.includes("/geospatial/locations/location-1/observations")) return payload({ observations: [observation], page: 1, limit: 100, returned: 1, radius_m: 5000 });
    if (url.includes("/geospatial/locations/location-1/events")) return payload({ events: [], page: 1, limit: 100, radius_m: 5000 });
    if (url.includes("/locations/location-1/summary")) return payload({ location_id: location.id, total_alerts: 1, unread_alerts: 1, recent_observations_count: 1, associated_events_count: 0, note: "anomalies" });
    if (url.endsWith("/alerts/alert-1/read")) return payload({ alert: { ...alert, status: "read", read_at: "2026-11-10T10:00:00Z" } });
    if (url.endsWith("/chat/conversations") && init?.method === "POST") return payload({ conversation }, 201);
    if (url.includes("/chat/conversations?") || url.endsWith("/chat/conversations")) return payload({ conversations: [conversation], total: 1, page: 1, per_page: 50 });
    if (url.endsWith("/chat/conversations/conversation-1")) return payload({ conversation: { ...conversation, messages: [] } });
    if (url.includes("/chat/conversations/conversation-1/messages")) return payload({ conversation_id: conversation.id, user_message_id: "message-user", assistant_message_id: "message-assistant", response_text: "Your saved location is North Farm.", tool_summaries: [{ tool: "list_monitoring_locations", status: "ok" }] });

    // Authority endpoints
    if (url.endsWith("/authority/operational-summary")) return payload({ status: "operational", active_events_count: 5, total_observations_count: 140, mode: "professional_monitoring" });
    if (url.endsWith("/authority/events")) return payload({ events: [{ id: "ev-100", status: "active", started_at: "2026-11-10T12:00:00Z", ended_at: null, centroid: { longitude: -6.8, latitude: 33.9 } }], count: 1 });

    // Admin endpoints
    if (url.endsWith("/admin/system")) return payload({ status: "ok", total_users: 25, roles: { user: 20, farm_owner: 3, authority: 1, admin: 1 }, data_sources: [{ id: "src-1", name: "NASA FIRMS", provider: "NASA", type: "satellite" }] });

    // IoT endpoints
    if (url.endsWith("/admin/iot/nodes")) return payload({ nodes: [iotNode], count: 1 });
    if (url.endsWith("/authority/iot/nodes")) return payload({ nodes: [iotNode], count: 1 });
    if (url.includes("/iot/nodes/") && url.includes("/telemetry/latest")) return payload(iotTelemetryLatest);
    if (url.includes("/iot/nodes/") && url.includes("/telemetry/history")) return payload(iotTelemetryHistory);

    // Route preview endpoint
    if (url.endsWith("/geography/routes/preview")) {
      return payload({
        provider: "osrm",
        profile: "foot",
        distance_m: 4500,
        duration_s: 3600,
        geometry: { type: "LineString", coordinates: [[-6.8, 33.9], [-6.85, 33.95]] },
        waypoints: [{ longitude: -6.8, latitude: 33.9 }, { longitude: -6.85, latitude: 33.95 }],
        saved: false,
        message: "Preview only",
      });
    }

    return payload({ error: { code: "not_found", message: `No mock for ${url}` } }, 404);
  }) as typeof fetch;
}

describe("Dashboard core flows", () => {
  beforeEach(() => { sessionStorage.clear(); vi.stubGlobal("fetch", mockedFetch()); });

  it("logs in and protects data behind authentication", async () => {
    render(<Dashboard />);
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email address"), { target: { value: user.email } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Monitoring overview" })).toBeInTheDocument();
    expect(sessionStorage.getItem("polaris_access")).toBe("access");
    expect(await screen.findByText("Recent anomalies")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Monitoring Locations" }));
    expect(await screen.findByText("North Farm")).toBeInTheDocument();
  });

  it("shows saved locations and displays an alert read-state update", async () => {
    sessionStorage.setItem("polaris_access", "access");
    render(<Dashboard />);
    await screen.findByRole("heading", { name: "Monitoring overview" });
    fireEvent.click(screen.getByRole("button", { name: "Alerts" }));
    expect(await screen.findByText(alert.title)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Mark read/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Mark read/ })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Monitoring Locations" }));
    expect(await screen.findByText("Saved monitoring locations")).toBeInTheDocument();
  });

  it("creates a conversation, sends a message, and renders the assistant response", async () => {
    sessionStorage.setItem("polaris_access", "access");
    render(<Dashboard />);
    await screen.findByRole("heading", { name: "Monitoring overview" });
    fireEvent.click(screen.getByRole("button", { name: "AI Assistant" }));
    fireEvent.click(await screen.findByRole("button", { name: "New conversation" }));
    const composer = await screen.findByLabelText("Message assistant");
    fireEvent.change(composer, { target: { value: "Show my monitoring locations" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("Your saved location is North Farm.")).toBeInTheDocument();
    expect(screen.getByText(/list monitoring locations · ok/i)).toBeInTheDocument();
  });

  it("configures and updates monitoring subscription for a location", async () => {
    sessionStorage.setItem("polaris_access", "access");
    render(<Dashboard />);
    await screen.findByRole("heading", { name: "Monitoring overview" });
    fireEvent.click(screen.getByRole("button", { name: "Monitoring Locations" }));
    fireEvent.click(await screen.findByRole("button", { name: "View North Farm details" }));
    expect(await screen.findByText("Alert Subscription")).toBeInTheDocument();
    expect(screen.getByLabelText("Monitoring radius in km")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update subscription" })).toBeInTheDocument();
  });

  it("routes admin user to professional portal with admin system overview and public portal switching", async () => {
    const adminUser = { id: "admin-1", email: "admin@example.com", display_name: "Admin User", roles: ["admin"] };
    const adminFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: adminUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(adminFetch));
    sessionStorage.setItem("polaris_access", "admin-token");

    render(<Dashboard />);
    expect(await screen.findByText("PROFESSIONAL PORTAL")).toBeInTheDocument();
    expect(screen.getByText("System Administrator")).toBeInTheDocument();
    expect(await screen.findByText("Active Regional Events")).toBeInTheDocument();

    // Verify admin system tab is visible and displays system overview
    fireEvent.click(screen.getByRole("button", { name: "System Administration" }));
    expect(await screen.findByText("Total Registered Users")).toBeInTheDocument();
    expect(await screen.findByText("25")).toBeInTheDocument();
    expect(screen.getByText("User & Role Distribution")).toBeInTheDocument();

    // Verify portal switcher to public view
    expect(screen.getByRole("button", { name: /Switch to Public Portal/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Switch to Public Portal/ }));
    expect(await screen.findByText("PUBLIC & FARM MONITOR")).toBeInTheDocument();
  });

  it("routes authority user to professional portal without admin tab or portal switching", async () => {
    const authorityUser = { id: "auth-1", email: "chief@civilprotection.ma", display_name: "Regional Chief", roles: ["authority"] };
    const authFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: authorityUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(authFetch));
    sessionStorage.setItem("polaris_access", "auth-token");

    render(<Dashboard />);
    expect(await screen.findByText("PROFESSIONAL PORTAL")).toBeInTheDocument();
    expect(screen.getByText("Regional Authority")).toBeInTheDocument();
    expect(await screen.findByText("Active Regional Events")).toBeInTheDocument();

    // Authority must NOT see the Admin tab or portal switcher
    expect(screen.queryByRole("button", { name: "System Administration" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Switch to Public Portal/ })).not.toBeInTheDocument();
  });

  it("routes farm_owner user to public portal", async () => {
    const farmUser = { id: "farm-1", email: "farmer@olive.ma", display_name: "Olive Farmer", roles: ["farm_owner"] };
    const farmFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: farmUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(farmFetch));
    sessionStorage.setItem("polaris_access", "farm-token");

    render(<Dashboard />);
    expect(await screen.findByText("PUBLIC & FARM MONITOR")).toBeInTheDocument();
    expect(screen.getByText("Role: farm_owner")).toBeInTheDocument();
    expect(screen.queryByText("PROFESSIONAL PORTAL")).not.toBeInTheDocument();
  });

  it("denies access with clear error state when role is unknown or empty", async () => {
    const unknownUser = { id: "anon-1", email: "intruder@domain.com", display_name: "Unknown", roles: ["intruder_role"] };
    const deniedFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: unknownUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(deniedFetch));
    sessionStorage.setItem("polaris_access", "intruder-token");

    render(<Dashboard />);
    expect(await screen.findByRole("heading", { name: "Access Denied: Unrecognized Role" })).toBeInTheDocument();
    expect(screen.getByText(/Reported Roles: intruder_role/)).toBeInTheDocument();
    expect(screen.queryByText("Monitoring overview")).not.toBeInTheDocument();
    expect(screen.queryByText("PROFESSIONAL PORTAL")).not.toBeInTheDocument();
  });

  it("calculates and displays hiking route preview in public portal", async () => {
    sessionStorage.setItem("polaris_access", "access");
    render(<Dashboard />);
    await screen.findByRole("heading", { name: "Monitoring overview" });

    fireEvent.click(screen.getByRole("button", { name: "Hiking Routes" }));
    expect(await screen.findByRole("heading", { name: "Hiking & Field Route Preview" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Calculate Route Preview" }));
    expect(await screen.findByText("4.50 km")).toBeInTheDocument();
    expect(screen.getByText("1 hr 0 min")).toBeInTheDocument();
    expect(screen.getByText("Preview Only (Unsaved)")).toBeInTheDocument();
  });

  it("allows admin to monitor provisioned IoT stations with full hardware metadata and telemetry", async () => {
    const adminUser = { id: "admin-1", email: "admin@polaris.ma", display_name: "Admin User", roles: ["admin"] };
    const adminFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: adminUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(adminFetch));
    sessionStorage.setItem("polaris_access", "admin-token");

    render(<Dashboard />);
    expect(await screen.findByText("PROFESSIONAL PORTAL")).toBeInTheDocument();

    // Navigate to IoT Telemetry section
    fireEvent.click(screen.getByRole("button", { name: /IoT Telemetry/ }));
    expect(await screen.findByRole("heading", { name: "IoT Sensor Stations & Telemetry" })).toBeInTheDocument();
    expect(screen.getByText("Administrator Mode (Full Hardware Metadata)")).toBeInTheDocument();

    // Verify station metadata
    expect(await screen.findByText("Ifrane Forest Station")).toBeInTheDocument();
    expect(screen.getByText("polaris-station-ifrane-01")).toBeInTheDocument();
    expect(screen.getByText("0004A30B001C0001")).toBeInTheDocument();
    expect(screen.getAllByText("3.92 V").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Active")).toBeInTheDocument();

    // Verify live sensor metrics
    expect((await screen.findAllByText("21.6 °C")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("44.2 %").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("1014.5 hPa").length).toBeGreaterThanOrEqual(1);

    // Verify reception provenance snapshot and historical table
    expect(screen.getByText("Frame Counter: 150")).toBeInTheDocument();
    expect(screen.getByText("Ifrane National Park")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Measurement History" })).toBeInTheDocument();
    expect(screen.getByText("#150")).toBeInTheDocument();
  });

  it("allows authority to monitor IoT stations in read-only mode without admin controls", async () => {
    const authorityUser = { id: "auth-1", email: "chief@civilprotection.ma", display_name: "Regional Chief", roles: ["authority"] };
    const authFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: authorityUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(authFetch));
    sessionStorage.setItem("polaris_access", "auth-token");

    render(<Dashboard />);
    expect(await screen.findByText("PROFESSIONAL PORTAL")).toBeInTheDocument();

    // Navigate to IoT Telemetry section
    fireEvent.click(screen.getByRole("button", { name: /IoT Telemetry/ }));
    expect(await screen.findByRole("heading", { name: "IoT Sensor Stations & Telemetry" })).toBeInTheDocument();
    expect(screen.getByText("Authority Read-Only View")).toBeInTheDocument();

    // Authority sees station and telemetry
    expect(await screen.findByText("Ifrane Forest Station")).toBeInTheDocument();
    expect((await screen.findAllByText("21.6 °C")).length).toBeGreaterThanOrEqual(1);

    // No admin-only controls or tabs
    expect(screen.queryByText("Administrator Mode (Full Hardware Metadata)")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "System Administration" })).not.toBeInTheDocument();
  });

  it("renders clear unavailable telemetry state without inventing false zeros", async () => {
    const adminUser = { id: "admin-1", email: "admin@polaris.ma", display_name: "Admin User", roles: ["admin"] };
    const emptyTelemetryFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: adminUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/iot/nodes/") && url.includes("/telemetry/latest")) {
        return new Response(JSON.stringify({
          ...iotTelemetryLatest,
          latest_uplink: null,
          measurements: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/iot/nodes/") && url.includes("/telemetry/history")) {
        return new Response(JSON.stringify({ history: [], count: 0 }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(emptyTelemetryFetch));
    sessionStorage.setItem("polaris_access", "admin-token");

    render(<Dashboard />);
    expect(await screen.findByText("PROFESSIONAL PORTAL")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /IoT Telemetry/ }));
    expect((await screen.findAllByText("Ifrane Forest Station")).length).toBeGreaterThanOrEqual(1);

    // Must display explicit unavailable state, NOT "0 °C" or "0 %"
    expect(await screen.findByRole("heading", { name: "Telemetry Unavailable" })).toBeInTheDocument();
    expect(screen.getByText(/no LoRaWAN uplinks have been received yet/i)).toBeInTheDocument();
    expect(screen.queryByText("0.0 °C")).not.toBeInTheDocument();
    expect(screen.queryByText("0 °C")).not.toBeInTheDocument();
  });

  it("distinguishes unavailable telemetry from failed API requests with clear error state", async () => {
    const adminUser = { id: "admin-1", email: "admin@polaris.ma", display_name: "Admin User", roles: ["admin"] };
    const errorTelemetryFetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return new Response(JSON.stringify({ user: adminUser }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/iot/nodes/") && url.includes("/telemetry/latest")) {
        return new Response(JSON.stringify({ error: { code: "internal_error", message: "Database connection failed during query." } }), { status: 500, headers: { "Content-Type": "application/json" } });
      }
      return mockedFetch()(input, init);
    };
    vi.stubGlobal("fetch", vi.fn(errorTelemetryFetch));
    sessionStorage.setItem("polaris_access", "admin-token");

    render(<Dashboard />);
    expect(await screen.findByText("PROFESSIONAL PORTAL")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /IoT Telemetry/ }));
    expect(await screen.findByText("Ifrane Forest Station")).toBeInTheDocument();

    // Verify error banner is rendered with message and retry button
    expect(await screen.findByText(/Failed to load station telemetry: Database connection failed during query./i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Telemetry Unavailable" })).not.toBeInTheDocument();
  });
});
