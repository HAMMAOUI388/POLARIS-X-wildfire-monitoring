"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowRightLeft,
  CheckCircle2,
  Database,
  Flame,
  Globe2,
  LoaderCircle,
  Lock,
  LogOut,
  Battery,
  Droplets,
  Gauge,
  History,
  Menu,
  Radio,
  RefreshCw,
  Server,
  Shield,
  ShieldAlert,
  Thermometer,
  Users,
  X,
} from "lucide-react";
import {
  IoTHistoryItem,
  IoTLatestTelemetry,
  IoTNode,
  IoTTelemetryMeasurement,
  OperationalSummary,
  PolarisApi,
  RegionalEvent,
  SystemOverview,
  User,
} from "@/lib/api";
import type { EventPin } from "@/components/map-view";

const MapView = dynamic(() => import("@/components/map-view"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[420px] items-center justify-center rounded-[22px] bg-[#edf1eb] text-sm text-[#637b70]">
      Preparing the operational map…
    </div>
  ),
});

type ProfessionalSection = "Operational Summary" | "Regional Fire Events" | "Operational Map" | "IoT Telemetry" | "System Administration";

type Props = {
  api: PolarisApi;
  user: User;
  isAdmin: boolean;
  canSwitchToPublic: boolean;
  onSwitchPortal?: (portal: "public" | "professional") => void;
  onLogout: () => void;
};

export function ProfessionalPortal({
  api,
  user,
  isAdmin,
  canSwitchToPublic,
  onSwitchPortal,
  onLogout,
}: Props) {
  const [section, setSection] = useState<ProfessionalSection>("Operational Summary");
  const [mobileNav, setMobileNav] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [summary, setSummary] = useState<OperationalSummary | null>(null);
  const [events, setEvents] = useState<RegionalEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<RegionalEvent | null>(null);
  const [eventDetail, setEventDetail] = useState<{ id: string; status: string; started_at: string; ended_at: string | null; centroid: { longitude: number; latitude: number }; classification: string } | null>(null);
  const [eventDetailLoading, setEventDetailLoading] = useState(false);

  const [systemOverview, setSystemOverview] = useState<SystemOverview | null>(null);
  const [adminLoading, setAdminLoading] = useState(false);

  const [iotNodes, setIotNodes] = useState<IoTNode[]>([]);
  const [selectedIoTNodeId, setSelectedIoTNodeId] = useState<string | null>(null);
  const [iotNodesLoading, setIotNodesLoading] = useState(false);
  const [iotNodesError, setIotNodesError] = useState("");

  const [latestTelemetry, setLatestTelemetry] = useState<IoTLatestTelemetry | null>(null);
  const [telemetryHistory, setTelemetryHistory] = useState<IoTHistoryItem[]>([]);
  const [telemetryLoading, setTelemetryLoading] = useState(false);
  const [telemetryError, setTelemetryError] = useState("");

  const refreshOperationalData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [sumRes, evRes] = await Promise.all([
        api.authoritySummary(),
        api.authorityEvents(),
      ]);
      setSummary(sumRes);
      setEvents(evRes.events);
    } catch (reason) {
      setError((reason as Error).message || "Could not load operational authority data.");
    } finally {
      setLoading(false);
    }
  }, [api]);

  const loadAdminSystem = useCallback(async () => {
    if (!isAdmin) return;
    setAdminLoading(true);
    try {
      const sys = await api.adminSystem();
      setSystemOverview(sys);
    } catch (reason) {
      setError((reason as Error).message || "Could not load administrative system overview.");
    } finally {
      setAdminLoading(false);
    }
  }, [api, isAdmin]);

  const loadIoTNodes = useCallback(async () => {
    setIotNodesLoading(true);
    setIotNodesError("");
    try {
      const res = isAdmin ? await api.adminIoTNodes() : await api.authorityIoTNodes();
      setIotNodes(res.nodes);
      if (res.nodes.length > 0) {
        setSelectedIoTNodeId(prev => (prev && res.nodes.some(n => n.id === prev) ? prev : res.nodes[0].id));
      } else {
        setSelectedIoTNodeId(null);
      }
    } catch (reason) {
      setIotNodesError((reason as Error).message || "Could not load IoT sensor stations.");
    } finally {
      setIotNodesLoading(false);
    }
  }, [api, isAdmin]);

  const loadNodeTelemetry = useCallback(async (nodeId: string) => {
    setTelemetryLoading(true);
    setTelemetryError("");
    try {
      const [latestRes, historyRes] = await Promise.all([
        api.iotNodeLatestTelemetry(nodeId),
        api.iotNodeTelemetryHistory(nodeId, 50),
      ]);
      setLatestTelemetry(latestRes);
      setTelemetryHistory(historyRes.history);
    } catch (reason) {
      setTelemetryError((reason as Error).message || "Could not load station telemetry.");
      setLatestTelemetry(null);
      setTelemetryHistory([]);
    } finally {
      setTelemetryLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refreshOperationalData();
  }, [refreshOperationalData]);

  useEffect(() => {
    if (section === "System Administration" && isAdmin) {
      void loadAdminSystem();
    }
  }, [section, isAdmin, loadAdminSystem]);

  useEffect(() => {
    if (section === "IoT Telemetry") {
      void loadIoTNodes();
    }
  }, [section, loadIoTNodes]);

  useEffect(() => {
    if (section === "IoT Telemetry" && selectedIoTNodeId) {
      void loadNodeTelemetry(selectedIoTNodeId);
    }
  }, [section, selectedIoTNodeId, loadNodeTelemetry]);

  const inspectEvent = async (ev: RegionalEvent) => {
    setSelectedEvent(ev);
    setEventDetail(null);
    setEventDetailLoading(true);
    try {
      const res = await api.eventDetails(ev.id);
      setEventDetail(res.event);
    } catch {
      // Event may have no linked alert recipient in current scope; keep base ev
    } finally {
      setEventDetailLoading(false);
    }
  };

  const eventPins: EventPin[] = events
    .filter(e => e.centroid !== null)
    .map(e => ({
      id: e.id,
      status: e.status,
      started_at: e.started_at,
      point: e.centroid || undefined,
    }));

  const navItems: { name: ProfessionalSection; icon: typeof Activity; adminOnly?: boolean }[] = [
    { name: "Operational Summary", icon: Activity },
    { name: "Regional Fire Events", icon: Flame },
    { name: "Operational Map", icon: Globe2 },
    { name: "IoT Telemetry", icon: Radio },
    { name: "System Administration", icon: Shield, adminOnly: true },
  ];

  const formatTime = (value: string | null) => {
    if (!value) return "Ongoing / Active";
    return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  };

  const selectedNode = iotNodes.find(n => n.id === selectedIoTNodeId);
  const tempMeas = latestTelemetry?.measurements?.find(m => m.unit === "°C" || m.sensor_identifier?.includes("temp"));
  const humMeas = latestTelemetry?.measurements?.find(m => m.unit === "%" || m.sensor_identifier?.includes("humid"));
  const pressMeas = latestTelemetry?.measurements?.find(m => m.unit === "hPa" || m.sensor_identifier?.includes("press"));

  const formatMeasurement = (meas: IoTTelemetryMeasurement | undefined, fallbackUnit: string) => {
    if (!meas || meas.value_numeric === null || meas.value_numeric === undefined) {
      return "Unavailable";
    }
    return `${meas.value_numeric.toFixed(1)} ${meas.unit || fallbackUnit}`;
  };

  const renderStatusBadge = (status: string) => {
    const norm = status?.toLowerCase();
    if (norm === "active") {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[#e8f5ed] px-2.5 py-0.5 text-xs font-semibold text-[#1f6e43]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#2da462]" />
          Active
        </span>
      );
    }
    if (norm === "retired") {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fef5e7] px-2.5 py-0.5 text-xs font-semibold text-[#965a0e]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#d98218]" />
          Retired
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fbebeb] px-2.5 py-0.5 text-xs font-semibold text-[#a32727]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#d63a3a]" />
        {status || "Unknown"}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-[#f3f5f2] text-ink">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[270px] flex-col border-r border-[#dbe2da] bg-[#142823] px-4 py-5 text-white transition-transform lg:translate-x-0 ${
          mobileNav ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#285e50] text-[#86d4aa]">
              <Radio className="h-5 w-5" />
            </div>
            <div>
              <div className="text-[13px] font-bold tracking-[.14em]">POLARIS X</div>
              <div className="text-[9px] font-semibold tracking-[.18em] text-[#8ea499]">
                PROFESSIONAL PORTAL
              </div>
            </div>
          </div>
          <button
            aria-label="Close navigation"
            onClick={() => setMobileNav(false)}
            className="text-white/60 hover:text-white lg:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-7 rounded-xl bg-white/5 p-3 text-xs border border-white/10">
          <div className="text-[10px] uppercase tracking-wider text-white/50">Operator Status</div>
          <div className="mt-1 flex items-center gap-2 font-semibold text-[#8de2b3]">
            <span className="h-2 w-2 rounded-full bg-[#46c281]" />
            {isAdmin ? "System Administrator" : "Regional Authority"}
          </div>
          <div className="mt-1 truncate text-[10px] text-white/60">{user.email}</div>
        </div>

        <div className="mb-2 mt-6 px-3 text-[10px] font-bold uppercase tracking-[.16em] text-[#789184]">
          Command Operations
        </div>

        <nav className="space-y-1">
          {navItems.map(item => {
            // Strictly hide System Administration tab from non-admin users
            if (item.adminOnly && !isAdmin) return null;

            const Icon = item.icon;
            const active = section === item.name;
            return (
              <button
                key={item.name}
                onClick={() => {
                  setSection(item.name);
                  setMobileNav(false);
                }}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[13px] font-medium transition ${
                  active
                    ? "bg-[#285e50] text-white font-semibold"
                    : "text-white/70 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1">{item.name}</span>
                {item.name === "Regional Fire Events" && events.length > 0 && (
                  <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-bold text-white/90">
                    {events.length}
                  </span>
                )}
                {item.name === "IoT Telemetry" && iotNodes.length > 0 && (
                  <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-bold text-white/90">
                    {iotNodes.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {canSwitchToPublic && (
          <div className="mt-5 border-t border-white/10 pt-4">
            <button
              onClick={() => onSwitchPortal?.("public")}
              className="flex w-full items-center gap-2.5 rounded-xl border border-[#3b6b5e] bg-white/5 px-3 py-2 text-left text-xs font-semibold text-[#9ae3be] hover:bg-white/10"
            >
              <ArrowRightLeft className="h-4 w-4" />
              <span>Switch to Public Portal</span>
            </button>
          </div>
        )}

        <div className="mt-auto space-y-3">
          <div className="rounded-xl bg-white/5 p-3 text-[11px] leading-5 text-white/60 border border-white/10">
            <div className="flex items-center gap-1.5 font-semibold text-white/80">
              <ShieldAlert className="h-3.5 w-3.5 text-[#ffab85]" />
              Authority Notice
            </div>
            Regional events are derived from clustered satellite detections. They represent thermal activity, not
            ground-verified fire perimeters.
          </div>

          <button
            onClick={onLogout}
            className="flex w-full items-center gap-2 rounded-xl bg-white/5 px-3 py-2.5 text-xs font-semibold text-[#f7a28e] hover:bg-white/10"
          >
            <LogOut className="h-4 w-4" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {mobileNav && (
        <button
          aria-label="Close menu backdrop"
          onClick={() => setMobileNav(false)}
          className="fixed inset-0 z-30 bg-[#0c1a1780] lg:hidden"
        />
      )}

      {/* Main content */}
      <div className="lg:pl-[270px]">
        {/* Header */}
        <header className="sticky top-0 z-20 flex h-[70px] items-center justify-between border-b border-[#dbe3db] bg-white/95 px-4 backdrop-blur md:px-8">
          <div className="flex items-center gap-3">
            <button
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
              className="rounded-lg p-2 hover:bg-[#f3f6f2] lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div>
              <div className="text-sm font-semibold">{section}</div>
              <div className="text-[11px] text-[#7e9086]">
                Operational Command · Morocco Regional Scope
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-[#dce5dc] bg-[#f7faf7] px-3 py-1 text-[11px] font-medium text-[#466a58] sm:flex">
              <span className="h-2 w-2 rounded-full bg-[#3ca970]" /> Mode: {summary?.mode || "professional"}
            </span>

            <button
              onClick={() => void refreshOperationalData()}
              disabled={loading}
              className="flex items-center gap-1.5 rounded-xl border border-[#d8e2d8] px-3 py-1.5 text-xs font-semibold text-[#446654] hover:bg-[#f5f8f4] disabled:opacity-50"
            >
              <Activity className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] px-4 py-6 md:px-8 md:py-8">
          {error && (
            <div role="alert" className="mb-5 flex items-center justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}><X className="h-4 w-4" /></button>
            </div>
          )}

          {/* Section 1: Operational Summary */}
          {section === "Operational Summary" && (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[#708479]">Active Regional Events</span>
                    <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#fff0e9] text-[#de6d44]">
                      <Flame className="h-4 w-4" />
                    </div>
                  </div>
                  <div className="mt-3 text-3xl font-bold tracking-tight text-[#172e27]">
                    {summary?.active_events_count ?? "—"}
                  </div>
                  <div className="mt-1 text-[11px] text-[#86978e]">
                    Ongoing satellite-clustered fire events
                  </div>
                </div>

                <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[#708479]">Total Observations Ingested</span>
                    <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#e8f1f8] text-[#4180a2]">
                      <Database className="h-4 w-4" />
                    </div>
                  </div>
                  <div className="mt-3 text-3xl font-bold tracking-tight text-[#172e27]">
                    {summary?.total_observations_count?.toLocaleString() ?? "—"}
                  </div>
                  <div className="mt-1 text-[11px] text-[#86978e]">
                    NASA FIRMS thermal anomalies on record
                  </div>
                </div>

                <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[#708479]">Operational Health</span>
                    <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#eaf4ed] text-[#337b54]">
                      <CheckCircle2 className="h-4 w-4" />
                    </div>
                  </div>
                  <div className="mt-3 text-2xl font-bold tracking-tight capitalize text-[#172e27]">
                    {summary?.status || "operational"}
                  </div>
                  <div className="mt-1 text-[11px] text-[#86978e]">
                    Backend intelligence engine active
                  </div>
                </div>
              </div>

              {/* Quick links & recent regional events */}
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
                <section className="rounded-[22px] border border-[#e2e8e1] bg-white p-6 shadow-card">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-base font-semibold">Active Regional Fire Events</h2>
                      <p className="mt-0.5 text-xs text-[#86978e]">
                        Latest clustered satellite detections across Morocco
                      </p>
                    </div>
                    <button
                      onClick={() => setSection("Regional Fire Events")}
                      className="text-xs font-semibold text-[#1f6652] hover:underline"
                    >
                      View all ({events.length})
                    </button>
                  </div>

                  <div className="mt-4 divide-y divide-[#edf1ea]">
                    {events.slice(0, 5).map(ev => (
                      <div key={ev.id} className="flex items-center justify-between py-3">
                        <div className="flex items-center gap-3">
                          <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#fff0e9] text-[#de6d44]">
                            <Flame className="h-4 w-4" />
                          </div>
                          <div>
                            <div className="text-xs font-semibold text-[#1b342d]">
                              Event {ev.id.slice(0, 8)}…
                            </div>
                            <div className="mt-0.5 text-[10px] text-[#83948b]">
                              Started {formatTime(ev.started_at)} · Status: {ev.status}
                            </div>
                          </div>
                        </div>

                        <button
                          onClick={() => {
                            inspectEvent(ev);
                            setSection("Regional Fire Events");
                          }}
                          className="rounded-lg border border-[#dbe3db] px-2.5 py-1 text-[11px] font-semibold text-[#547363] hover:bg-[#f6f9f5]"
                        >
                          Inspect
                        </button>
                      </div>
                    ))}

                    {events.length === 0 && (
                      <div className="py-8 text-center text-xs text-[#8c9c93]">
                        No regional fire events currently returned by the authority endpoint.
                      </div>
                    )}
                  </div>
                </section>

                <section className="rounded-[22px] border border-[#e2e8e1] bg-white p-6 shadow-card space-y-4">
                  <h3 className="text-sm font-semibold">Authority Standard Operating Procedures</h3>
                  <div className="rounded-xl bg-[#f8faf7] p-4 text-xs leading-5 text-[#5e7368] space-y-2 border border-[#e4ebe3]">
                    <div className="font-semibold text-[#1b342d]">Data Provenance & Policy</div>
                    <p>
                      1. Thermal anomalies are detected by spaceborne radiometers. Ground dispatch requires local validation.
                    </p>
                    <p>
                      2. Clustered events connect nearby satellite detections across space and time.
                    </p>
                    <p>
                      3. Operational reports must state that detections are thermal anomalies, not confirmed wildfires.
                    </p>
                  </div>

                  <button
                    onClick={() => setSection("Operational Map")}
                    className="w-full rounded-xl bg-[#1b4e42] py-3 text-center text-xs font-semibold text-white hover:bg-[#143e34]"
                  >
                    Open Regional Operational Map
                  </button>
                </section>
              </div>
            </div>
          )}

          {/* Section 2: Regional Fire Events */}
          {section === "Regional Fire Events" && (
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
              <section className="rounded-[22px] border border-[#e2e8e1] bg-white p-6 shadow-card">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-semibold">Regional Fire Event Registry</h2>
                    <p className="mt-0.5 text-xs text-[#86978e]">
                      Clustered fire events from `GET /api/v1/authority/events`
                    </p>
                  </div>
                  <span className="rounded-full bg-[#f2f6f2] px-3 py-1 text-xs font-semibold text-[#416a56]">
                    {events.length} records
                  </span>
                </div>

                <div className="mt-5 overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#edf0eb] text-[#86988f]">
                        <th className="pb-3 font-semibold">Event ID</th>
                        <th className="pb-3 font-semibold">Status</th>
                        <th className="pb-3 font-semibold">Started At</th>
                        <th className="pb-3 font-semibold">Centroid</th>
                        <th className="pb-3 font-semibold text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#edf0eb]">
                      {events.map(ev => (
                        <tr
                          key={ev.id}
                          className={`hover:bg-[#f8faf7] ${selectedEvent?.id === ev.id ? "bg-[#eef5f0]" : ""}`}
                        >
                          <td className="py-3 font-medium text-[#1c3830]">{ev.id.slice(0, 8)}…</td>
                          <td className="py-3">
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                ev.status === "active"
                                  ? "bg-[#fff0e9] text-[#cf6741]"
                                  : "bg-[#f0f4ef] text-[#617c6e]"
                              }`}
                            >
                              {ev.status}
                            </span>
                          </td>
                          <td className="py-3 text-[#6c8075]">{formatTime(ev.started_at)}</td>
                          <td className="py-3 text-[#6c8075]">
                            {ev.centroid
                              ? `${ev.centroid.latitude.toFixed(4)}, ${ev.centroid.longitude.toFixed(4)}`
                              : "No centroid"}
                          </td>
                          <td className="py-3 text-right">
                            <button
                              onClick={() => inspectEvent(ev)}
                              className="rounded-lg border border-[#dce4dc] px-2.5 py-1 text-[11px] font-semibold text-[#3b6653] hover:bg-white"
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {events.length === 0 && (
                    <div className="py-12 text-center text-xs text-[#8c9c93]">
                      No regional events found.
                    </div>
                  )}
                </div>
              </section>

              {/* Event detail inspector */}
              <section className="rounded-[22px] border border-[#e2e8e1] bg-white p-6 shadow-card">
                <h3 className="text-base font-semibold">Event Intelligence Inspector</h3>
                <p className="mt-0.5 text-xs text-[#86978e]">
                  Detailed telemetry for selected regional event
                </p>

                {selectedEvent ? (
                  <div className="mt-5 space-y-4">
                    <div className="rounded-xl bg-[#f7f9f5] p-4 border border-[#e8ece5]">
                      <div className="text-[10px] uppercase tracking-wider text-[#86978e]">Event Identifier</div>
                      <div className="mt-1 font-mono text-xs font-semibold text-[#1c3830]">{selectedEvent.id}</div>
                      <div className="mt-3 flex items-center gap-2">
                        <span className="rounded-full bg-[#fff0e9] px-2 py-0.5 text-[10px] font-bold text-[#c96039]">
                          Status: {selectedEvent.status}
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-xl border border-[#edf0eb] p-3">
                        <div className="text-[10px] text-[#86978e]">Start Timestamp</div>
                        <div className="mt-1 font-semibold text-[#224238]">{formatTime(selectedEvent.started_at)}</div>
                      </div>
                      <div className="rounded-xl border border-[#edf0eb] p-3">
                        <div className="text-[10px] text-[#86978e]">End Timestamp</div>
                        <div className="mt-1 font-semibold text-[#224238]">{formatTime(selectedEvent.ended_at)}</div>
                      </div>
                    </div>

                    {selectedEvent.centroid && (
                      <div className="rounded-xl border border-[#edf0eb] p-3 text-xs">
                        <div className="text-[10px] text-[#86978e]">Calculated Centroid Coordinates</div>
                        <div className="mt-1 font-semibold text-[#224238]">
                          {selectedEvent.centroid.latitude.toFixed(5)}, {selectedEvent.centroid.longitude.toFixed(5)}
                        </div>
                      </div>
                    )}

                    {eventDetailLoading ? (
                      <div className="flex items-center gap-2 text-xs text-[#6e8579] py-3">
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                        Fetching alert corroboration…
                      </div>
                    ) : eventDetail ? (
                      <div className="rounded-xl bg-[#f5f8f5] p-3.5 text-xs border border-[#e0ebe2]">
                        <div className="font-semibold text-[#1e4d3f]">Corroborated Alert Classification</div>
                        <p className="mt-1 text-[11px] text-[#63796d]">{eventDetail.classification}</p>
                      </div>
                    ) : null}

                    <div className="rounded-xl bg-[#fffaf5] border border-[#f7e6d7] p-3 text-[11px] leading-5 text-[#8f5a34]">
                      Geospatially clustered event. It does not provide confirmed wildfire diagnosis or fire spread modeling.
                    </div>
                  </div>
                ) : (
                  <div className="py-16 text-center text-xs text-[#8c9c93]">
                    Select an event from the registry to inspect its operational data.
                  </div>
                )}
              </section>
            </div>
          )}

          {/* Section 3: Operational Map */}
          {section === "Operational Map" && (
            <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
              <div className="flex items-center justify-between pb-4 border-b border-[#edf0eb]">
                <div>
                  <h2 className="text-base font-semibold">Regional Operational Map</h2>
                  <p className="mt-0.5 text-xs text-[#86978e]">
                    Geospatial centroids of all reported regional events
                  </p>
                </div>
                <div className="flex items-center gap-4 text-xs text-[#62776c]">
                  <span className="flex items-center gap-1.5">
                    <i className="h-2.5 w-2.5 rounded-full bg-[#7a5ae0]" /> Regional Event Centroid
                  </span>
                </div>
              </div>

              <div className="mt-4 h-[550px]">
                <MapView
                  locations={[]}
                  observations={[]}
                  events={eventPins}
                  selectedPoint={null}
                  onSelectEvent={ev => {
                    const matched = events.find(e => e.id === ev.id);
                    if (matched) inspectEvent(matched);
                  }}
                />
              </div>

              <div className="mt-4 text-[11px] text-[#84968c]">
                Showing {eventPins.length} event centroids. Click an event pin to inspect record details.
              </div>
            </div>
          )}

          {/* Section: IoT Telemetry */}
          {section === "IoT Telemetry" && (
            <div className="space-y-6">
              {/* Header */}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-lg font-bold text-[#1b342d]">IoT Sensor Stations & Telemetry</h2>
                  <p className="mt-0.5 text-xs text-[#7e9186]">
                    Terrestrial LoRaWAN sensor nodes · Ground-truth microclimate monitoring
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-bold ${
                      isAdmin
                        ? "bg-[#e8f3ec] text-[#256649]"
                        : "bg-[#f0f4ef] text-[#486356]"
                    }`}
                  >
                    {isAdmin ? "Administrator Mode (Full Hardware Metadata)" : "Authority Read-Only View"}
                  </span>
                  <button
                    onClick={() => {
                      void loadIoTNodes();
                      if (selectedIoTNodeId) void loadNodeTelemetry(selectedIoTNodeId);
                    }}
                    disabled={iotNodesLoading || telemetryLoading}
                    className="flex items-center gap-1.5 rounded-xl border border-[#d8e2d8] bg-white px-3 py-1.5 text-xs font-semibold text-[#446654] hover:bg-[#f5f8f4] disabled:opacity-50"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${iotNodesLoading || telemetryLoading ? "animate-spin" : ""}`} />
                    <span>Refresh Telemetry</span>
                  </button>
                </div>
              </div>

              {/* Station Selection / Overview */}
              {iotNodesLoading ? (
                <div className="flex items-center justify-center p-12 text-xs text-[#6e8579]">
                  <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                  Loading provisioned sensor stations…
                </div>
              ) : iotNodesError ? (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-700">
                  Failed to load IoT stations: {iotNodesError}
                </div>
              ) : iotNodes.length === 0 ? (
                <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-8 text-center text-xs text-[#708479]">
                  No provisioned IoT sensor stations found.
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Stations Cards List */}
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {iotNodes.map(node => {
                      const isSelected = node.id === selectedIoTNodeId;
                      return (
                        <div
                          key={node.id}
                          onClick={() => setSelectedIoTNodeId(node.id)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setSelectedIoTNodeId(node.id); }}
                          className={`cursor-pointer rounded-[20px] border p-5 transition shadow-card text-left ${
                            isSelected
                              ? "border-[#285e50] bg-white ring-2 ring-[#285e50]/20"
                              : "border-[#e2e8e1] bg-white hover:border-[#b8c9be]"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="text-sm font-bold text-[#193229]">{node.name}</div>
                              <div className="font-mono text-[11px] text-[#708579]">{node.node_identifier}</div>
                            </div>
                            <div>{renderStatusBadge(node.status)}</div>
                          </div>

                          <div className="mt-4 space-y-1.5 text-xs text-[#526a5d]">
                            <div className="flex items-center justify-between">
                              <span className="text-[#84978d]">DevEUI</span>
                              <span className="font-mono font-medium text-[#253f34]">{node.dev_eui || "—"}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[#84978d]">Battery</span>
                              <span className="font-semibold text-[#253f34]">
                                {node.battery_voltage !== null && node.battery_voltage !== undefined
                                  ? `${node.battery_voltage.toFixed(2)} V`
                                  : "—"}
                              </span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[#84978d]">Last Seen</span>
                              <span className="text-[#253f34]">{node.last_seen_at ? formatTime(node.last_seen_at) : "Never"}</span>
                            </div>

                            {/* Admin-only metadata */}
                            {isAdmin && (
                              <div className="mt-2 pt-2 border-t border-[#edf1ea] space-y-1 text-[11px]">
                                <div className="flex items-center justify-between">
                                  <span className="text-[#84978d]">Last Frame (FCnt)</span>
                                  <span className="font-mono text-[#253f34]">{node.last_f_cnt ?? "—"}</span>
                                </div>
                                <div className="flex items-center justify-between">
                                  <span className="text-[#84978d]">Location ID</span>
                                  <span className="font-mono text-[10px] text-[#253f34] truncate max-w-[140px]">
                                    {node.location_id || "Unassigned"}
                                  </span>
                                </div>
                              </div>
                            )}

                            {/* Authority-only metadata */}
                            {!isAdmin && node.location && (
                              <div className="mt-2 pt-2 border-t border-[#edf1ea] text-[11px]">
                                <span className="text-[#84978d]">Location: </span>
                                <span className="font-medium text-[#253f34]">{node.location.name}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Telemetry Detail Section for Selected Node */}
                  {selectedNode && (
                    <div className="space-y-6">
                      {telemetryLoading ? (
                        <div className="flex items-center justify-center p-12 text-xs text-[#6e8579]">
                          <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                          Loading telemetry and reception history for {selectedNode.name}…
                        </div>
                      ) : telemetryError ? (
                        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-700 flex items-center justify-between">
                          <span>Failed to load station telemetry: {telemetryError}</span>
                          <button
                            onClick={() => loadNodeTelemetry(selectedNode.id)}
                            className="rounded-lg bg-red-100 px-2.5 py-1 text-xs font-semibold hover:bg-red-200"
                          >
                            Retry
                          </button>
                        </div>
                      ) : !latestTelemetry?.latest_uplink || latestTelemetry.measurements.length === 0 ? (
                        /* Explicit unavailable data state: distinguished from request failure, no zero values! */
                        <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-8 text-center space-y-2 shadow-card">
                          <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#edf3ef] text-[#4b6d5c]">
                            <Radio className="h-6 w-6" />
                          </div>
                          <h3 className="text-sm font-bold text-[#1b342d]">Telemetry Unavailable</h3>
                          <p className="mx-auto max-w-md text-xs leading-5 text-[#708479]">
                            Station <span className="font-semibold text-[#1f372e]">{selectedNode.name}</span> is registered, but no LoRaWAN uplinks have been received yet. Sensor readings and gateway provenance will populate once the station transmits.
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-6">
                          {/* Live Sensor Metrics Grid */}
                          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            {/* Temperature */}
                            <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-[#708479]">Ambient Temperature</span>
                                <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#fff2eb] text-[#d96738]">
                                  <Thermometer className="h-4 w-4" />
                                </div>
                              </div>
                              <div className="mt-3 text-2xl font-bold tracking-tight text-[#172e27]">
                                {formatMeasurement(tempMeas, "°C")}
                              </div>
                              <div className="mt-1 flex items-center justify-between text-[11px] text-[#86978e]">
                                <span>Quality: {tempMeas?.quality_flag || "—"}</span>
                                <span>{tempMeas?.sensor_identifier || "BME280"}</span>
                              </div>
                            </div>

                            {/* Humidity */}
                            <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-[#708479]">Relative Humidity</span>
                                <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#eaf4fb] text-[#327fa8]">
                                  <Droplets className="h-4 w-4" />
                                </div>
                              </div>
                              <div className="mt-3 text-2xl font-bold tracking-tight text-[#172e27]">
                                {formatMeasurement(humMeas, "%")}
                              </div>
                              <div className="mt-1 flex items-center justify-between text-[11px] text-[#86978e]">
                                <span>Quality: {humMeas?.quality_flag || "—"}</span>
                                <span>{humMeas?.sensor_identifier || "BME280"}</span>
                              </div>
                            </div>

                            {/* Pressure */}
                            <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-[#708479]">Barometric Pressure</span>
                                <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#edf5ef] text-[#2e8254]">
                                  <Gauge className="h-4 w-4" />
                                </div>
                              </div>
                              <div className="mt-3 text-2xl font-bold tracking-tight text-[#172e27]">
                                {formatMeasurement(pressMeas, "hPa")}
                              </div>
                              <div className="mt-1 flex items-center justify-between text-[11px] text-[#86978e]">
                                <span>Quality: {pressMeas?.quality_flag || "—"}</span>
                                <span>{pressMeas?.sensor_identifier || "BME280"}</span>
                              </div>
                            </div>

                            {/* Battery & Signal */}
                            <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-[#708479]">Battery & Radio Link</span>
                                <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#f2f4f1] text-[#4d6a5c]">
                                  <Battery className="h-4 w-4" />
                                </div>
                              </div>
                              <div className="mt-3 text-2xl font-bold tracking-tight text-[#172e27]">
                                {latestTelemetry.battery_voltage !== null && latestTelemetry.battery_voltage !== undefined
                                  ? `${latestTelemetry.battery_voltage.toFixed(2)} V`
                                  : "Unavailable"}
                              </div>
                              <div className="mt-1 flex items-center justify-between text-[11px] text-[#86978e]">
                                <span>
                                  {latestTelemetry.latest_uplink.rssi_dbm !== null && latestTelemetry.latest_uplink.rssi_dbm !== undefined
                                    ? `${latestTelemetry.latest_uplink.rssi_dbm} dBm`
                                    : "RSSI —"}
                                </span>
                                <span>
                                  {latestTelemetry.latest_uplink.snr_db !== null && latestTelemetry.latest_uplink.snr_db !== undefined
                                    ? `${latestTelemetry.latest_uplink.snr_db.toFixed(1)} dB SNR`
                                    : "SNR —"}
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Reception Provenance & Location Snapshot */}
                          <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card space-y-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Radio className="h-4 w-4 text-[#306854]" />
                                <span className="text-xs font-bold text-[#1b342d]">Packet Reception Provenance</span>
                              </div>
                              <span className="text-[11px] font-mono text-[#788e83]">
                                Frame Counter: {latestTelemetry.latest_uplink.f_cnt ?? "—"}
                              </span>
                            </div>
                            <div className="grid gap-3 sm:grid-cols-3 text-xs">
                              <div className="rounded-xl bg-[#f8faf8] p-3 border border-[#edf1ea]">
                                <div className="text-[10px] text-[#788e83] uppercase tracking-wider">LNS Reception Time</div>
                                <div className="mt-1 font-medium text-[#1c362d]">
                                  {latestTelemetry.latest_uplink.lns_received_at
                                    ? formatTime(latestTelemetry.latest_uplink.lns_received_at)
                                    : "—"}
                                </div>
                              </div>
                              <div className="rounded-xl bg-[#f8faf8] p-3 border border-[#edf1ea]">
                                <div className="text-[10px] text-[#788e83] uppercase tracking-wider">Location Snapshot</div>
                                <div className="mt-1 font-medium text-[#1c362d] truncate">
                                  {latestTelemetry.latest_uplink.location_snapshot?.name || "Unassigned"}
                                </div>
                              </div>
                              <div className="rounded-xl bg-[#f8faf8] p-3 border border-[#edf1ea]">
                                <div className="text-[10px] text-[#788e83] uppercase tracking-wider">Ingestion Coordinates (SRID 4326)</div>
                                <div className="mt-1 font-mono text-[11px] text-[#1c362d]">
                                  {latestTelemetry.latest_uplink.location_snapshot?.point
                                    ? `${latestTelemetry.latest_uplink.location_snapshot.point.latitude.toFixed(4)}°N, ${latestTelemetry.latest_uplink.location_snapshot.point.longitude.toFixed(4)}°W`
                                    : "Not recorded"}
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Historical Uplink Table */}
                          <div className="rounded-[22px] border border-[#e2e8e1] bg-white p-5 shadow-card space-y-4">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <History className="h-4 w-4 text-[#306854]" />
                                <h3 className="text-xs font-bold text-[#1b342d]">Measurement History</h3>
                              </div>
                              <span className="text-xs text-[#788e83]">
                                Showing last {telemetryHistory.length} uplink transmission(s)
                              </span>
                            </div>

                            {telemetryHistory.length === 0 ? (
                              <div className="py-6 text-center text-xs text-[#708479]">
                                No historical uplinks recorded for this station.
                              </div>
                            ) : (
                              <div className="overflow-x-auto">
                                <table className="w-full text-left text-xs">
                                  <thead>
                                    <tr className="border-b border-[#edf1ea] text-[10px] uppercase tracking-wider text-[#788e83]">
                                      <th className="pb-2.5 font-semibold">Frame (FCnt)</th>
                                      <th className="pb-2.5 font-semibold">LNS Received At</th>
                                      <th className="pb-2.5 font-semibold">Temperature</th>
                                      <th className="pb-2.5 font-semibold">Humidity</th>
                                      <th className="pb-2.5 font-semibold">Pressure</th>
                                      <th className="pb-2.5 font-semibold">Radio Link</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-[#edf1ea]">
                                    {telemetryHistory.map(item => {
                                      const t = item.measurements.find(m => m.unit === "°C" || m.sensor_identifier?.includes("temp"));
                                      const h = item.measurements.find(m => m.unit === "%" || m.sensor_identifier?.includes("humid"));
                                      const p = item.measurements.find(m => m.unit === "hPa" || m.sensor_identifier?.includes("press"));

                                      return (
                                        <tr key={item.uplink_id} className="hover:bg-[#f9fbf9]">
                                          <td className="py-2.5 font-mono text-[#253f34]">#{item.f_cnt}</td>
                                          <td className="py-2.5 text-[#253f34]">{formatTime(item.lns_received_at)}</td>
                                          <td className="py-2.5 font-medium text-[#253f34]">
                                            {t && t.value !== null && t.value !== undefined ? `${t.value.toFixed(1)} °C` : "—"}
                                          </td>
                                          <td className="py-2.5 font-medium text-[#253f34]">
                                            {h && h.value !== null && h.value !== undefined ? `${h.value.toFixed(1)} %` : "—"}
                                          </td>
                                          <td className="py-2.5 font-medium text-[#253f34]">
                                            {p && p.value !== null && p.value !== undefined ? `${p.value.toFixed(1)} hPa` : "—"}
                                          </td>
                                          <td className="py-2.5 font-mono text-[11px] text-[#708579]">
                                            {item.rssi_dbm !== null ? `${item.rssi_dbm} dBm` : "—"} / {item.snr_db !== null ? `${item.snr_db.toFixed(1)} dB` : "—"}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Section 4: System Administration (Admin ONLY) */}
          {section === "System Administration" && (
            <div>
              {!isAdmin ? (
                /* Strict Access Denied if an authority tries to manipulate state to admin tab */
                <div className="rounded-[22px] border border-[#f3d7ce] bg-white p-8 text-center shadow-card">
                  <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-[#fff0e9] text-[#de5732]">
                    <Lock className="h-7 w-7" />
                  </div>
                  <h2 className="mt-4 text-lg font-bold text-[#2a1a15]">Administrative Privilege Required</h2>
                  <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-[#826e67]">
                    This section is strictly restricted to accounts with the <code className="bg-red-50 px-1 py-0.5 rounded text-red-800">admin</code> role.
                    Regional authorities cannot access user distributions or internal system settings.
                  </p>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-lg font-bold text-[#1b342d]">System Administration & Overview</h2>
                      <p className="mt-0.5 text-xs text-[#7e9186]">
                        Privileged platform metrics from `GET /api/v1/admin/system`
                      </p>
                    </div>
                    <span className="rounded-full bg-[#e8f3ec] px-3 py-1 text-xs font-bold text-[#256649]">
                      Administrator Mode Active
                    </span>
                  </div>

                  {adminLoading ? (
                    <div className="flex items-center justify-center p-12 text-xs text-[#6e8579]">
                      <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                      Loading system overview…
                    </div>
                  ) : systemOverview ? (
                    <div className="grid gap-6 lg:grid-cols-2">
                      {/* Users & Roles */}
                      <section className="rounded-[22px] border border-[#e2e8e1] bg-white p-6 shadow-card space-y-4">
                        <div className="flex items-center gap-3">
                          <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#eaf3ee] text-[#256649]">
                            <Users className="h-5 w-5" />
                          </div>
                          <div>
                            <h3 className="text-sm font-semibold">User & Role Distribution</h3>
                            <p className="text-[11px] text-[#86978e]">Registered accounts across security roles</p>
                          </div>
                        </div>

                        <div className="rounded-xl bg-[#f7faf7] p-4 border border-[#e5ebe4]">
                          <div className="text-xs text-[#788e82]">Total Registered Users</div>
                          <div className="mt-1 text-3xl font-extrabold text-[#173027]">
                            {systemOverview.total_users}
                          </div>
                        </div>

                        <div className="space-y-2">
                          <div className="text-xs font-semibold text-[#506659]">Role Distribution</div>
                          <div className="divide-y divide-[#edf1ea] rounded-xl border border-[#edf1ea]">
                            {Object.entries(systemOverview.roles).map(([rName, count]) => (
                              <div key={rName} className="flex items-center justify-between px-3 py-2.5 text-xs">
                                <span className="font-mono text-[#25463b]">{rName}</span>
                                <span className="rounded-full bg-[#f0f4ef] px-2.5 py-0.5 font-semibold text-[#486356]">
                                  {count} users
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </section>

                      {/* Ingested Data Sources */}
                      <section className="rounded-[22px] border border-[#e2e8e1] bg-white p-6 shadow-card space-y-4">
                        <div className="flex items-center gap-3">
                          <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#e8f1f8] text-[#34789b]">
                            <Server className="h-5 w-5" />
                          </div>
                          <div>
                            <h3 className="text-sm font-semibold">Configured Data Sources</h3>
                            <p className="text-[11px] text-[#86978e]">External satellite and geospatial pipelines</p>
                          </div>
                        </div>

                        <div className="space-y-2.5">
                          {systemOverview.data_sources.map(ds => (
                            <div key={ds.id} className="rounded-xl border border-[#edf1ea] p-3.5 text-xs space-y-1">
                              <div className="flex items-center justify-between font-semibold text-[#1d382f]">
                                <span>{ds.name}</span>
                                <span className="rounded bg-[#f0f4ef] px-2 py-0.5 text-[10px] text-[#556e61] uppercase">
                                  {ds.type}
                                </span>
                              </div>
                              <div className="text-[11px] text-[#7d9086]">Provider: {ds.provider}</div>
                              <div className="font-mono text-[9px] text-[#9baa9f]">Source ID: {ds.id}</div>
                            </div>
                          ))}

                          {systemOverview.data_sources.length === 0 && (
                            <div className="py-8 text-center text-xs text-[#8c9c93]">
                              No active data sources reported by backend.
                            </div>
                          )}
                        </div>
                      </section>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
