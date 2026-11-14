import { describe, expect, it, vi } from "vitest";
import { evaluateRoles, PolarisApi } from "./api";

describe("evaluateRoles strict role classification", () => {
  it("routes admin to professional portal with public switching enabled", () => {
    const res = evaluateRoles(["admin"]);
    expect(res.portal).toBe("professional");
    expect(res.isAdmin).toBe(true);
    expect(res.canSwitchToPublic).toBe(true);
    expect(res.hasRecognizedRole).toBe(true);
  });

  it("routes authority to professional portal without admin privileges or switching", () => {
    const res = evaluateRoles(["authority"]);
    expect(res.portal).toBe("professional");
    expect(res.isAdmin).toBe(false);
    expect(res.isAuthority).toBe(true);
    expect(res.canSwitchToPublic).toBe(false);
    expect(res.hasRecognizedRole).toBe(true);
  });

  it("routes farm_owner to public portal", () => {
    const res = evaluateRoles(["farm_owner"]);
    expect(res.portal).toBe("public");
    expect(res.isFarmOwner).toBe(true);
    expect(res.isAdmin).toBe(false);
    expect(res.canSwitchToPublic).toBe(false);
  });

  it("routes user to public portal", () => {
    const res = evaluateRoles(["user"]);
    expect(res.portal).toBe("public");
    expect(res.isUser).toBe(true);
    expect(res.isAdmin).toBe(false);
  });

  it("denies access for missing, empty, or unknown roles", () => {
    expect(evaluateRoles(null).portal).toBe("denied");
    expect(evaluateRoles(undefined).portal).toBe("denied");
    expect(evaluateRoles([]).portal).toBe("denied");
    expect(evaluateRoles(["guest"]).portal).toBe("denied");
    expect(evaluateRoles(["hacker", "unknown"]).portal).toBe("denied");
  });
});

describe("PolarisApi", () => {
  it("returns structured API errors without losing the backend message", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "not_found", message: "Alert not found." } }), { status: 404 }));
    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    api.setTokens("access", "refresh");
    await expect(api.alert("missing")).rejects.toMatchObject({ status: 404, code: "not_found", message: "Alert not found." });
  });

  it("registers a new account and returns the created user", async () => {
    const createdUser = { id: "u-new", email: "new@example.com", display_name: "New Person", roles: ["user"] };
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ user: createdUser }), { status: 201, headers: { "Content-Type": "application/json" } })
    );
    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    const result = await api.register("new@example.com", "StrongPassword1234!", "New Person");
    expect(result.user.email).toBe("new@example.com");
    expect(result.user.roles).toEqual(["user"]);
    expect(fetcher).toHaveBeenCalledWith(
      "http://backend/api/v1/auth/register",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ email: "new@example.com", password: "StrongPassword1234!", display_name: "New Person" }) })
    );
  });

  it("surfaces a 409 conflict error from duplicate-email registration", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "conflict", message: "The request conflicts with existing data." } }), { status: 409 })
    );
    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    await expect(api.register("existing@example.com", "StrongPassword1234!", "Existing")).rejects.toMatchObject({
      status: 409,
      code: "conflict",
      message: "The request conflicts with existing data.",
    });
  });

  it("surfaces a 422 validation error from invalid registration input", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "validation_error", message: "Request validation failed." } }), { status: 422 })
    );
    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    await expect(api.register("bad", "short", "")).rejects.toMatchObject({ status: 422, code: "validation_error" });
  });

  it("reports a network failure during registration as a stable user-facing error", async () => {
    const api = new PolarisApi("http://backend/api/v1", { fetcher: vi.fn().mockRejectedValue(new TypeError("Failed to fetch")) as typeof fetch });
    await expect(api.register("x@example.com", "StrongPassword1234!", "X")).rejects.toMatchObject({
      code: "network_error",
      message: "Could not reach the POLARIS X server.",
    });
  });

  it("refreshes an expired access token and retries the original request", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new-access" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: { id: "u", email: "e", display_name: "Name", roles: ["user"] } }), { status: 200 }));
    const updated = vi.fn(); const api = new PolarisApi("http://backend/api/v1", { fetcher, onTokensUpdated: updated });
    api.setTokens("old-access", "refresh-token");
    await api.me();
    expect(api.getAccessToken()).toBe("new-access");
    expect(updated).toHaveBeenCalledWith("new-access");
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("reports network failures as a stable user-facing error", async () => {
    const api = new PolarisApi("http://backend/api/v1", { fetcher: vi.fn().mockRejectedValue(new TypeError("network details")) as typeof fetch });
    await expect(api.locations()).rejects.toMatchObject({ code: "network_error", message: "Could not reach the POLARIS X server." });
  });

  it("handles subscription management requests with bearer auth", async () => {
    const sub = { id: "sub-1", user_id: "u-1", location_id: "loc-1", route_id: null, radius_m: 5000, minimum_severity: "low", enabled: true };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ subscriptions: [sub] }), { status: 200 }));
    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    api.setTokens("token-xyz", null);
    const result = await api.subscriptions();
    expect(result.subscriptions).toHaveLength(1);
    expect(result.subscriptions[0].id).toBe("sub-1");
    expect(fetcher).toHaveBeenCalledWith(
      "http://backend/api/v1/subscriptions",
      expect.objectContaining({
        headers: expect.any(Headers),
      })
    );
  });

  it("fetches authority operational summary and regional events", async () => {
    const summary = { status: "operational", active_events_count: 3, total_observations_count: 42, mode: "professional_monitoring" };
    const events = { events: [{ id: "ev-1", status: "active", started_at: "2026-11-10T12:00:00Z", ended_at: null, centroid: { longitude: -6.8, latitude: 33.9 } }], count: 1 };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(summary), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(events), { status: 200 }));

    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    api.setTokens("token-auth", null);

    const s = await api.authoritySummary();
    expect(s.active_events_count).toBe(3);
    expect(fetcher).toHaveBeenNthCalledWith(1, "http://backend/api/v1/authority/operational-summary", expect.any(Object));

    const e = await api.authorityEvents();
    expect(e.count).toBe(1);
    expect(fetcher).toHaveBeenNthCalledWith(2, "http://backend/api/v1/authority/events", expect.any(Object));
  });

  it("fetches admin system overview", async () => {
    const overview = { status: "ok", total_users: 10, roles: { user: 8, admin: 2 }, data_sources: [] };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(overview), { status: 200 }));
    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    api.setTokens("token-admin", null);

    const res = await api.adminSystem();
    expect(res.total_users).toBe(10);
    expect(fetcher).toHaveBeenCalledWith("http://backend/api/v1/admin/system", expect.any(Object));
  });

  it("submits route preview request with foot profile", async () => {
    const previewResult = { provider: "osrm", profile: "foot", distance_m: 3500, duration_s: 2500, geometry: { type: "LineString", coordinates: [[-6.8, 33.9], [-6.81, 33.92]] }, waypoints: [{ longitude: -6.8, latitude: 33.9 }, { longitude: -6.81, latitude: 33.92 }], saved: false, message: "Preview only" };
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(previewResult), { status: 200 }));
    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    api.setTokens("token-user", null);

    const res = await api.previewRoute({
      origin: { longitude: -6.8, latitude: 33.9 },
      destination: { longitude: -6.81, latitude: 33.92 },
      profile: "foot",
    });
    expect(res.distance_m).toBe(3500);
    expect(res.saved).toBe(false);
    expect(fetcher).toHaveBeenCalledWith(
      "http://backend/api/v1/geography/routes/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ origin: { longitude: -6.8, latitude: 33.9 }, destination: { longitude: -6.81, latitude: 33.92 }, waypoints: [], profile: "foot" }),
      })
    );
  });

  it("fetches IoT endpoints for admin and authority roles", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ nodes: [{ id: "node-1", name: "Station Alpha", dev_eui: "0004A30B001C0001", status: "active" }], count: 1 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ nodes: [{ id: "node-1", name: "Station Alpha", dev_eui: "0004A30B001C0001", status: "active", location: { name: "Ifrane" } }], count: 1 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        node_id: "node-1",
        node_identifier: "node-alpha",
        name: "Station Alpha",
        status: "active",
        active: true,
        dev_eui: "0004A30B001C0001",
        battery_voltage: 3.95,
        last_seen_at: "2026-11-11T12:00:00Z",
        last_f_cnt: 42,
        latest_uplink: { id: "up-1", session_id: "sess-1", f_cnt: 42, lns_received_at: "2026-11-11T12:00:00Z", rssi_dbm: -80, snr_db: 9.5, gateway_count: 2, location_snapshot: { name: "Ifrane", point: { longitude: -5.1, latitude: 33.5 } } },
        measurements: [{ sensor_id: "s-1", sensor_kind: "bme280", sensor_identifier: "station_temp", value_numeric: 22.4, raw_value_numeric: 22.4, unit: "°C", raw_value_unit: "°C", quality_flag: "good", measured_at: null, received_at: "2026-11-11T12:00:00Z" }],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        history: [{ uplink_id: "up-1", f_cnt: 42, lns_received_at: "2026-11-11T12:00:00Z", rssi_dbm: -80, snr_db: 9.5, location_name: "Ifrane", location_point: { longitude: -5.1, latitude: 33.5 }, measurements: [{ sensor_identifier: "station_temp", kind: "bme280", value: 22.4, unit: "°C", quality_flag: "good" }] }],
        count: 1,
      }), { status: 200 }));

    const api = new PolarisApi("http://backend/api/v1", { fetcher });
    api.setTokens("token-test", null);

    const adminNodes = await api.adminIoTNodes();
    expect(adminNodes.count).toBe(1);
    expect(fetcher).toHaveBeenNthCalledWith(1, "http://backend/api/v1/admin/iot/nodes", expect.any(Object));

    const authNodes = await api.authorityIoTNodes();
    expect(authNodes.count).toBe(1);
    expect(fetcher).toHaveBeenNthCalledWith(2, "http://backend/api/v1/authority/iot/nodes", expect.any(Object));

    const latest = await api.iotNodeLatestTelemetry("node-1");
    expect(latest.name).toBe("Station Alpha");
    expect(latest.battery_voltage).toBe(3.95);
    expect(latest.measurements[0].value_numeric).toBe(22.4);
    expect(fetcher).toHaveBeenNthCalledWith(3, "http://backend/api/v1/iot/nodes/node-1/telemetry/latest", expect.any(Object));

    const hist = await api.iotNodeTelemetryHistory("node-1", 20);
    expect(hist.count).toBe(1);
    expect(hist.history[0].f_cnt).toBe(42);
    expect(fetcher).toHaveBeenNthCalledWith(4, "http://backend/api/v1/iot/nodes/node-1/telemetry/history?limit=20", expect.any(Object));
  });
});
