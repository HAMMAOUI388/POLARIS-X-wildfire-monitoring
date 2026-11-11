"use client";

import dynamic from "next/dynamic";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRightLeft,
  ArrowUpRight,
  Bell,
  Check,
  ChevronDown,
  CircleHelp,
  Compass,
  Flame,
  Footprints,
  Globe2,
  Info,
  Leaf,
  LoaderCircle,
  LogOut,
  MapPinned,
  Menu,
  MessageCircle,
  Plus,
  Search,
  Send,
  Settings2,
  Sparkles,
  ThermometerSun,
  Trash2,
  Wind,
  X,
} from "lucide-react";
import {
  Alert,
  ChatMessage,
  Conversation,
  Location,
  MonitoringSubscription,
  Observation,
  PlaceSearchResult,
  PolarisApi,
  RoutePreviewResult,
  User,
} from "@/lib/api";
import { RoutePreview } from "@/components/route-preview";
import type { EventPin, SelectedPoint } from "@/components/map-view";

const MapView = dynamic(() => import("@/components/map-view"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[420px] items-center justify-center rounded-[22px] bg-[#edf1eb] text-sm text-[#637b70]">
      Preparing the monitoring map…
    </div>
  ),
});

export type PublicSection =
  | "Overview"
  | "Live Monitoring Map"
  | "Monitoring Locations"
  | "Satellite Detections & Events"
  | "Alerts"
  | "Hiking Routes"
  | "Weather"
  | "AI Assistant"
  | "Account / Guidance";

const navItems: { name: PublicSection; icon: typeof Activity }[] = [
  { name: "Overview", icon: Activity },
  { name: "Live Monitoring Map", icon: Globe2 },
  { name: "Monitoring Locations", icon: MapPinned },
  { name: "Satellite Detections & Events", icon: Flame },
  { name: "Alerts", icon: Bell },
  { name: "Hiking Routes", icon: Footprints },
  { name: "Weather", icon: Wind },
  { name: "AI Assistant", icon: MessageCircle },
  { name: "Account / Guidance", icon: Settings2 },
];

const formatTime = (value: string) => new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
const shortId = (value: string) => `${value.slice(0, 8)}…`;

type Props = {
  api: PolarisApi;
  user: User;
  canSwitchToProfessional: boolean;
  onSwitchPortal?: (portal: "public" | "professional") => void;
  onLogout: () => void;
};

export function PublicPortal({
  api,
  user,
  canSwitchToProfessional,
  onSwitchPortal,
  onLogout,
}: Props) {
  const [section, setSection] = useState<PublicSection>("Overview");
  const [mobileNav, setMobileNav] = useState(false);
  const [dataLoading, setDataLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [locations, setLocations] = useState<Location[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [events, setEvents] = useState<EventPin[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [subscriptions, setSubscriptions] = useState<MonitoringSubscription[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const [locationSummaries, setLocationSummaries] = useState<
    Record<string, { total_alerts: number; unread_alerts: number; recent_observations_count: number; associated_events_count: number }>
  >({});

  const [selectedPoint, setSelectedPoint] = useState<SelectedPoint | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<Location | null>(null);
  const [selectedObservation, setSelectedObservation] = useState<Observation | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventPin | null>(null);

  // Route preview map overlay
  const [routeResult, setRouteResult] = useState<RoutePreviewResult | null>(null);

  // Search places
  const [searchText, setSearchText] = useState("");
  const [searchResults, setSearchResults] = useState<PlaceSearchResult[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [placeName, setPlaceName] = useState("");
  const [locationType, setLocationType] = useState("point");

  // Chatbot
  const [chatConversations, setChatConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatText, setChatText] = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  const refreshData = useCallback(async () => {
    setDataLoading(true);
    setError("");
    try {
      const [locationResult, alertResult, unreadResult, subResult] = await Promise.all([
        api.locations(),
        api.alerts(),
        api.alerts(1, 100, true),
        api.subscriptions().catch(() => ({ subscriptions: [] })),
      ]);
      setLocations(locationResult.locations);
      setAlerts(alertResult.alerts);
      setUnreadCount(unreadResult.total);
      setSubscriptions(subResult.subscriptions);

      const pieces = await Promise.all(
        locationResult.locations.map(async location => {
          const [detections, eventResult, summary] = await Promise.allSettled([
            api.observations(location.id),
            api.events(location.id),
            api.locationSummary(location.id),
          ]);
          return {
            location,
            detections: detections.status === "fulfilled" ? detections.value.observations : [],
            rawEvents: eventResult.status === "fulfilled" ? eventResult.value.events : [],
            summary: summary.status === "fulfilled" ? summary.value : null,
          };
        })
      );
      const foundObservations = pieces.flatMap(item => item.detections);
      const foundEvents = pieces.flatMap(item => item.rawEvents);
      const eventDetails = await Promise.allSettled(foundEvents.map(event => api.eventDetails(event.id)));
      const eventPins: EventPin[] = eventDetails.flatMap(result =>
        result.status === "fulfilled"
          ? [{ id: result.value.event.id, status: result.value.event.status, started_at: result.value.event.started_at, point: result.value.event.centroid }]
          : []
      );
      setObservations(foundObservations);
      setEvents(eventPins);
      setLocationSummaries(Object.fromEntries(pieces.flatMap(item => (item.summary ? [[item.location.id, item.summary]] : []))));
    } catch (reason) {
      setError((reason as Error).message || "Could not load dashboard data.");
    } finally {
      setDataLoading(false);
    }
  }, [api]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  const searchPlaces = async (event: FormEvent) => {
    event.preventDefault();
    if (searchText.trim().length < 2) return;
    setSearchBusy(true);
    setError("");
    try {
      setSearchResults((await api.searchPlaces(searchText.trim())).results);
    } catch (reason) {
      setError((reason as Error).message);
      setSearchResults([]);
    } finally {
      setSearchBusy(false);
    }
  };

  const saveSelectedPoint = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedPoint || !placeName.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.createLocation({
        name: placeName.trim(),
        location_type: locationType,
        longitude: selectedPoint.longitude,
        latitude: selectedPoint.latitude,
      });
      setPlaceName("");
      setSelectedPoint(null);
      await refreshData();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const renameLocation = async (location: Location, name: string) => {
    if (location.owner_id !== user.id || !name.trim()) return;
    setBusy(true);
    try {
      await api.updateLocation(location.id, {
        name: name.trim(),
        location_type: location.location_type,
        longitude: location.point.longitude,
        latitude: location.point.latitude,
        description: location.description || undefined,
      });
      setSelectedLocation(null);
      await refreshData();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const removeLocation = async (location: Location) => {
    if (location.owner_id !== user.id || !window.confirm(`Remove “${location.name}” from your monitored locations?`)) return;
    try {
      await api.deleteLocation(location.id);
      setSelectedLocation(null);
      await refreshData();
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const handleSaveSubscription = async (locationId: string, radius_m: number, minimum_severity: string, enabled: boolean) => {
    setError("");
    try {
      const existing = subscriptions.find(s => s.location_id === locationId);
      if (existing) {
        const res = await api.updateSubscription(existing.id, { radius_m, minimum_severity, enabled });
        setSubscriptions(prev => prev.map(s => (s.id === existing.id ? res.subscription : s)));
      } else {
        const res = await api.createSubscription({ location_id: locationId, radius_m, minimum_severity, enabled });
        setSubscriptions(prev => [...prev, res.subscription]);
      }
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const handleDeleteSubscription = async (subscriptionId: string) => {
    setError("");
    try {
      await api.deleteSubscription(subscriptionId);
      setSubscriptions(prev => prev.filter(s => s.id !== subscriptionId));
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const selectConversation = async (conversation: Conversation) => {
    setActiveConversation(conversation);
    setChatMessages([]);
    setChatBusy(true);
    try {
      setChatMessages((await api.conversation(conversation.id)).conversation.messages || []);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setChatBusy(false);
    }
  };

  const createConversation = async () => {
    setChatBusy(true);
    setError("");
    try {
      const result = await api.createConversation();
      setChatConversations(current => [result.conversation, ...current.filter(item => item.id !== result.conversation.id)]);
      setActiveConversation(result.conversation);
      setChatMessages([]);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setChatBusy(false);
    }
  };

  const sendChat = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeConversation || !chatText.trim()) return;
    const text = chatText.trim();
    setChatText("");
    setChatBusy(true);
    setError("");
    try {
      const result = await api.sendMessage(activeConversation.id, text);
      setChatMessages(current => [
        ...current,
        { id: result.user_message_id, role: "user", content: text, created_at: new Date().toISOString(), tool_summaries: [] },
        { id: result.assistant_message_id, role: "assistant", content: result.response_text, created_at: new Date().toISOString(), tool_summaries: result.tool_summaries },
      ]);
    } catch (reason) {
      setError((reason as Error).message);
      setChatText(text);
    } finally {
      setChatBusy(false);
    }
  };

  const loadConversations = useCallback(async () => {
    try {
      setChatConversations((await api.conversations()).conversations);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }, [api]);

  useEffect(() => {
    if (section === "AI Assistant") void loadConversations();
  }, [section, loadConversations]);

  const archiveConversation = async (conversation: Conversation) => {
    try {
      await api.archiveConversation(conversation.id);
      setChatConversations(current => current.filter(item => item.id !== conversation.id));
      if (activeConversation?.id === conversation.id) {
        setActiveConversation(null);
        setChatMessages([]);
      }
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const markRead = async (alert: Alert) => {
    try {
      const result = await api.markAlertRead(alert.id);
      setAlerts(current => current.map(item => (item.id === alert.id ? result.alert : item)));
      setUnreadCount(current => Math.max(0, current - (alert.status === "unread" ? 1 : 0)));
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const selectLocation = useCallback((location: Location) => {
    setSelectedLocation(location);
    setSelectedObservation(null);
    setSelectedEvent(null);
  }, []);

  const selectObservation = useCallback((item: Observation) => {
    setSelectedObservation(item);
    setSelectedLocation(null);
    setSelectedEvent(null);
  }, []);

  const selectEvent = useCallback((item: EventPin) => {
    setSelectedEvent(item);
    setSelectedLocation(null);
    setSelectedObservation(null);
  }, []);

  const mapEvents = useMemo(() => events, [events]);

  // Extract authentic weather evidence from received alerts
  const weatherEvidenceRecords = useMemo(() => {
    const list: { alertTitle: string; createdAt: string; evidence: Record<string, unknown> }[] = [];
    for (const a of alerts) {
      for (const ev of a.evidence || []) {
        if (ev.type === "weather_forecast" || ev.type === "weather_observation") {
          list.push({ alertTitle: a.title, createdAt: a.created_at, evidence: ev.details });
        }
      }
    }
    return list;
  }, [alerts]);

  const recentObservations = [...observations].sort((a, b) => b.observed_at.localeCompare(a.observed_at)).slice(0, 5);
  const pageTitle = section === "Overview" ? "Monitoring overview" : section;

  return (
    <div className="min-h-screen bg-[#f7f8f4] text-ink">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[260px] flex-col border-r border-[#e8ece6] bg-white px-4 py-5 transition-transform lg:translate-x-0 ${
          mobileNav ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-[14px] bg-[#176b58]">
              <Compass className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="text-[14px] font-bold tracking-[.14em]">POLARIS X</div>
              <div className="mt-0.5 text-[9px] font-semibold tracking-[.15em] text-[#94a29b]">
                PUBLIC & FARM MONITOR
              </div>
            </div>
          </div>
          <button aria-label="Close navigation" onClick={() => setMobileNav(false)} className="lg:hidden">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-2 mt-7 px-3 text-[10px] font-bold uppercase tracking-[.16em] text-[#9aa79f]">Workspace</div>
        <nav className="space-y-1">
          {navItems.map(item => {
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
                  active ? "bg-[#e9f4ed] text-[#176b58]" : "text-[#64756c] hover:bg-[#f4f7f3] hover:text-ink"
                }`}
              >
                <Icon className="h-[17px] w-[17px]" />
                <span className="flex-1">{item.name}</span>
                {item.name === "Alerts" && unreadCount > 0 && (
                  <span className="rounded-full bg-[#fbe9e1] px-2 py-0.5 text-[10px] font-semibold text-[#bd5938]">
                    {unreadCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {canSwitchToProfessional && (
          <div className="mt-4 border-t border-[#edf0eb] pt-3">
            <button
              onClick={() => onSwitchPortal?.("professional")}
              className="flex w-full items-center gap-2 rounded-xl border border-[#d6e3d9] bg-[#f5f8f5] px-3 py-2 text-left text-xs font-semibold text-[#1e5d4e] hover:bg-[#ebf3ec]"
            >
              <ArrowRightLeft className="h-4 w-4" />
              <span>Switch to Professional Portal</span>
            </button>
          </div>
        )}

        <div className="mt-auto rounded-2xl bg-[#f3f7f1] p-4">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <div className="grid h-7 w-7 place-items-center rounded-lg bg-[#dcece0] text-[#176b58]">
              <Leaf className="h-4 w-4" />
            </div>
            Data Guidance
          </div>
          <p className="mt-2 text-[11px] leading-[1.55] text-[#718077]">
            Satellite detections are thermal anomalies, not confirmed fires. Weather context does not establish fire spread.
          </p>
        </div>
      </aside>

      {mobileNav && (
        <button aria-label="Close menu backdrop" onClick={() => setMobileNav(false)} className="fixed inset-0 z-30 bg-[#102c2780] lg:hidden" />
      )}

      {/* Main Content Area */}
      <div className="lg:pl-[260px]">
        <header className="sticky top-0 z-20 flex h-[70px] items-center justify-between border-b border-[#e7ece5] bg-white/95 px-4 backdrop-blur md:px-8">
          <div className="flex items-center gap-3">
            <button aria-label="Open navigation" onClick={() => setMobileNav(true)} className="rounded-lg p-2 hover:bg-[#f3f6f2] lg:hidden">
              <Menu className="h-5 w-5" />
            </button>
            <div>
              <div className="text-sm font-semibold">{pageTitle}</div>
              <div className="mt-0.5 text-[11px] text-[#92a098]">
                Public Situational Awareness · Morocco
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-[#e8eee8] px-3 py-1.5 text-[11px] text-[#677970] sm:flex">
              <span className="h-2 w-2 rounded-full bg-[#50ad74]" /> Role: {user.roles.join(", ") || "user"}
            </div>

            <button
              aria-label="View alerts"
              onClick={() => setSection("Alerts")}
              className="relative rounded-xl border border-[#e6ece6] p-2.5 text-[#64766c] hover:bg-[#f7faf6]"
            >
              <Bell className="h-4 w-4" />
              {unreadCount > 0 && (
                <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-[#de7653] px-1 text-[9px] font-bold text-white">
                  {unreadCount}
                </span>
              )}
            </button>

            <div className="flex items-center gap-2 border-l border-[#e8ece6] pl-3">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-[#deeee2] text-xs font-bold text-[#176b58]">
                {user.display_name.slice(0, 1).toUpperCase()}
              </div>
              <div className="hidden sm:block">
                <div className="max-w-[150px] truncate text-xs font-semibold">{user.display_name}</div>
                <div className="text-[10px] text-[#92a098]">{user.email}</div>
              </div>
              <button aria-label="Account options" onClick={() => setSection("Account / Guidance")}>
                <ChevronDown className="h-4 w-4 text-[#92a098]" />
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] px-4 py-6 md:px-8 md:py-8">
          {error && (
            <div role="alert" className="mb-5 flex items-center justify-between rounded-xl border border-[#f1d4c8] bg-[#fff5f1] px-4 py-3 text-sm text-[#a75032]">
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          {/* Persistent NASA FIRMS Education Banner */}
          <div className="mb-6 flex items-start gap-3 rounded-2xl border border-[#e6efe7] bg-[#f4f9f5] p-4 text-xs text-[#446353]">
            <Info className="h-5 w-5 shrink-0 text-[#176b58] mt-0.5" />
            <div className="leading-5">
              <span className="font-semibold text-[#174e40]">NASA FIRMS Satellite Observation Notice:</span>{" "}
              Thermal detections originate from NASA VIIRS and MODIS satellite sensors. They represent elevated thermal
              signatures (anomalies) from space, not independently confirmed wildfires. Agricultural burning, industry,
              and reflective soils can trigger anomalies.
            </div>
          </div>

          <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[.14em] text-[#4f8a6c]">PUBLIC MONITORING</div>
              <h1 className="mt-1 text-[26px] font-semibold tracking-[-.025em]">{pageTitle}</h1>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => void refreshData()}
                disabled={dataLoading}
                className="flex items-center gap-2 rounded-xl border border-[#e1e8e1] bg-white px-3 py-2 text-xs font-semibold text-[#4f655a] hover:bg-[#f7faf6] disabled:opacity-50"
              >
                <Activity className={`h-3.5 w-3.5 ${dataLoading ? "animate-pulse" : ""}`} /> Refresh
              </button>
            </div>
          </div>

          {/* Section: Overview & Live Map */}
          {(section === "Overview" || section === "Live Monitoring Map") && (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard icon={MapPinned} label="Monitoring locations" value={locations.length} tone="green" note="Saved places you can access" onClick={() => setSection("Monitoring Locations")} />
                <MetricCard icon={ThermometerSun} label="Recent anomalies" value={observations.length} tone="orange" note="Within 5 km · latest retrieved" onClick={() => setSection("Satellite Detections & Events")} />
                <MetricCard icon={Flame} label="Associated events" value={events.length} tone="purple" note="Geospatially clustered records" onClick={() => setSection("Satellite Detections & Events")} />
                <MetricCard icon={Bell} label="Unread alerts" value={unreadCount} tone="blue" note="Personal notifications" onClick={() => setSection("Alerts")} />
              </div>

              <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
                <section className="overflow-hidden rounded-[22px] border border-[#e5ebe4] bg-white shadow-card">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#edf0eb] px-5 py-4">
                    <div>
                      <h2 className="text-sm font-semibold">Live monitoring map</h2>
                      <p className="mt-1 text-[11px] text-[#8a9990]">Satellite thermal anomalies and saved locations</p>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-[#65766d]">
                      <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-[#e8754d]" /> Anomaly</span>
                      <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-[#7a5ae0]" /> Event</span>
                      <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-[#176b58]" /> Location</span>
                    </div>
                  </div>

                  <div className="relative h-[430px] p-3">
                    <MapView
                      locations={locations}
                      observations={observations}
                      events={mapEvents}
                      selectedPoint={selectedPoint}
                      routeGeometry={routeResult?.geometry as { type: string; coordinates: [number, number][] } | undefined}
                      routeWaypoints={routeResult?.waypoints}
                      onMapClick={setSelectedPoint}
                      onSelectLocation={selectLocation}
                      onSelectObservation={selectObservation}
                      onSelectEvent={selectEvent}
                    />

                    <div className="absolute left-6 top-6 z-10 flex w-[min(360px,calc(100%-56px))] flex-col gap-2">
                      <form onSubmit={searchPlaces} className="flex rounded-xl border border-[#dfe8df] bg-white p-1.5 shadow-lg shadow-[#1c3b3210]">
                        <Search className="ml-2 mt-2 h-4 w-4 shrink-0 text-[#82948a]" />
                        <input
                          aria-label="Search places"
                          value={searchText}
                          onChange={e => setSearchText(e.target.value)}
                          placeholder="Search a place in Morocco"
                          className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-xs outline-none"
                        />
                        <button disabled={searchBusy} className="rounded-lg bg-[#176b58] px-3 py-2 text-[11px] font-semibold text-white">
                          {searchBusy ? "…" : "Search"}
                        </button>
                      </form>
                      {searchResults.length > 0 && (
                        <div className="max-h-48 overflow-auto rounded-xl border border-[#e1e8e1] bg-white p-1 shadow-xl">
                          {searchResults.map(result => (
                            <button
                              key={result.provider_id}
                              onClick={() => {
                                setSelectedPoint(result.point);
                                setPlaceName(result.display_name.split(",")[0]);
                                setSearchResults([]);
                              }}
                              className="block w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-[#f1f6f1]"
                            >
                              <span className="block font-semibold">{result.display_name.split(",")[0]}</span>
                              <span className="mt-0.5 block truncate text-[10px] text-[#84938a]">{result.display_name}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#edf0eb] px-5 py-3 text-[10px] text-[#8a9990]">
                    <span>Observation search radius: 5 km · Map tiles © OpenStreetMap contributors</span>
                    {routeResult && (
                      <span className="text-blue-700 font-semibold">Active Route Preview Overlay ({resultDistance(routeResult)})</span>
                    )}
                  </div>
                </section>

                <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-5 shadow-card">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-sm font-semibold">Latest observations</h2>
                      <p className="mt-1 text-[11px] text-[#8a9990]">NASA FIRMS thermal anomalies</p>
                    </div>
                    <button onClick={() => setSection("Satellite Detections & Events")} className="text-[11px] font-semibold text-[#176b58]">
                      View all
                    </button>
                  </div>

                  <div className="mt-4 space-y-1">
                    {recentObservations.length ? (
                      recentObservations.map(item => (
                        <button
                          key={item.id}
                          onClick={() => {
                            selectObservation(item);
                            setSection("Live Monitoring Map");
                          }}
                          className="flex w-full gap-3 rounded-xl p-2.5 text-left hover:bg-[#f7f9f5]"
                        >
                          <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-[#fff0e9] text-[#d76d47]">
                            <ThermometerSun className="h-4 w-4" />
                          </div>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-semibold">Thermal anomaly · {item.product}</span>
                            <span className="mt-1 block text-[10px] text-[#89978e]">{formatTime(item.observed_at)}</span>
                            <span className="mt-1 block text-[10px] text-[#687d70]">
                              {(item.distance_m / 1000).toFixed(1)} km away · {item.confidence || "confidence unavailable"}
                            </span>
                          </span>
                        </button>
                      ))
                    ) : (
                      <EmptyState
                        icon={ThermometerSun}
                        title="No recent detections"
                        detail={locations.length ? "No observations were returned within the current map search radius." : "Add a monitoring location to start viewing nearby data."}
                      />
                    )}
                  </div>
                </section>
              </div>

              {selectedPoint && (
                <section className="mt-4 rounded-[18px] border border-[#dce8dd] bg-white p-4 shadow-card">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-semibold">Save selected point</div>
                      <div className="mt-1 text-[11px] text-[#87958c]">
                        {selectedPoint.latitude.toFixed(5)}, {selectedPoint.longitude.toFixed(5)}
                      </div>
                    </div>
                    <form onSubmit={saveSelectedPoint} className="flex flex-wrap items-center gap-2">
                      <input
                        aria-label="Location name"
                        required
                        value={placeName}
                        onChange={e => setPlaceName(e.target.value)}
                        placeholder="Location name"
                        className="w-40 rounded-lg border border-[#e0e7e0] px-3 py-2 text-xs outline-none focus:border-[#176b58]"
                      />
                      <select
                        aria-label="Location type"
                        value={locationType}
                        onChange={e => setLocationType(e.target.value)}
                        className="rounded-lg border border-[#e0e7e0] bg-white px-2 py-2 text-xs"
                      >
                        <option value="point">Point</option>
                        <option value="farm">Farm</option>
                        <option value="campsite">Campsite</option>
                        <option value="trailhead">Trailhead</option>
                        <option value="other">Other</option>
                      </select>
                      <button disabled={busy} className="flex items-center gap-1.5 rounded-lg bg-[#176b58] px-3 py-2 text-xs font-semibold text-white">
                        <Plus className="h-3.5 w-3.5" /> Save place
                      </button>
                      <button type="button" aria-label="Clear selected map point" onClick={() => setSelectedPoint(null)} className="rounded-lg p-2 text-[#7c8d83] hover:bg-[#f2f5f1]">
                        <X className="h-4 w-4" />
                      </button>
                    </form>
                  </div>
                </section>
              )}

              {selectedObservation && (
                <section aria-label="Observation details" className="mt-4 flex flex-wrap items-start justify-between gap-3 rounded-[18px] border border-[#f0ded5] bg-white p-4 shadow-card">
                  <div className="flex gap-3">
                    <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#fff0e9] text-[#d76d47]">
                      <ThermometerSun className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="text-xs font-semibold">Satellite thermal anomaly · {selectedObservation.product}</div>
                      <div className="mt-1 text-[11px] text-[#78877e]">
                        Source: NASA FIRMS · {formatTime(selectedObservation.observed_at)} · ID {selectedObservation.external_id}
                      </div>
                      <div className="mt-1 text-[11px] text-[#78877e]">
                        {selectedObservation.point.latitude.toFixed(5)}, {selectedObservation.point.longitude.toFixed(5)} · {(selectedObservation.distance_m / 1000).toFixed(2)} km · confidence {selectedObservation.confidence || "not supplied"}
                        {selectedObservation.frp ? ` · FRP ${selectedObservation.frp} MW` : ""}
                      </div>
                      <div className="mt-1 text-[10px] text-[#a46b51]">Thermal anomaly; not a confirmed wildfire.</div>
                    </div>
                  </div>
                  <button aria-label="Close observation details" onClick={() => setSelectedObservation(null)} className="rounded-lg p-1.5 text-[#829087] hover:bg-[#f5f7f4]">
                    <X className="h-4 w-4" />
                  </button>
                </section>
              )}

              {selectedEvent && (
                <section aria-label="Event details" className="mt-4 flex items-start justify-between gap-3 rounded-[18px] border border-[#e4def6] bg-white p-4 shadow-card">
                  <div>
                    <div className="text-xs font-semibold">Observed satellite-associated event</div>
                    <div className="mt-1 text-[11px] text-[#78877e]">
                      Status: {selectedEvent.status} · Started {formatTime(selectedEvent.started_at)} · ID {selectedEvent.id}
                    </div>
                    <div className="mt-1 text-[10px] text-[#746699]">This geospatial association is not confirmation of a wildfire.</div>
                  </div>
                  <button aria-label="Close event details" onClick={() => setSelectedEvent(null)} className="rounded-lg p-1.5 text-[#829087] hover:bg-[#f5f7f4]">
                    <X className="h-4 w-4" />
                  </button>
                </section>
              )}
            </>
          )}

          {/* Section: Monitoring Locations */}
          {section === "Monitoring Locations" && (
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_350px]">
              <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-5 shadow-card">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold">Saved monitoring locations</h2>
                    <p className="mt-1 text-[11px] text-[#8a9990]">Owner and shared locations available to your account</p>
                  </div>
                  <button onClick={() => { setSection("Live Monitoring Map"); setSelectedPoint(null); }} className="flex items-center gap-2 rounded-lg bg-[#176b58] px-3 py-2 text-xs font-semibold text-white">
                    <Plus className="h-3.5 w-3.5" /> Add on map
                  </button>
                </div>
                <div className="mt-4 space-y-2">
                  {locations.length ? (
                    locations.map(location => {
                      const sub = subscriptions.find(s => s.location_id === location.id);
                      return (
                        <div key={location.id} className="flex flex-wrap items-center gap-3 rounded-2xl border border-[#edf0eb] p-4">
                          <button onClick={() => { selectLocation(location); setSection("Live Monitoring Map"); }} className="grid h-10 w-10 place-items-center rounded-xl bg-[#e9f4ed] text-[#176b58]">
                            <MapPinned className="h-5 w-5" />
                          </button>
                          <button onClick={() => setSelectedLocation(location)} className="min-w-0 flex-1 text-left">
                            <div className="flex items-center gap-2">
                              <span className="truncate text-sm font-semibold">{location.name}</span>
                              {sub && (
                                <span className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${sub.enabled ? "bg-[#eaf4ed] text-[#33734f]" : "bg-[#f4efe8] text-[#916a44]"}`}>
                                  {sub.enabled ? `${(sub.radius_m / 1000).toFixed(1)} km` : "Paused"}
                                </span>
                              )}
                            </div>
                            <div className="mt-1 text-[11px] text-[#89978e]">
                              {location.location_type} · {location.point.latitude.toFixed(4)}, {location.point.longitude.toFixed(4)}
                            </div>
                          </button>
                          <div className="hidden gap-5 text-center sm:flex">
                            <div>
                              <div className="text-sm font-semibold">{locationSummaries[location.id]?.recent_observations_count ?? "—"}</div>
                              <div className="text-[9px] text-[#94a098]">detections</div>
                            </div>
                            <div>
                              <div className="text-sm font-semibold">{locationSummaries[location.id]?.associated_events_count ?? "—"}</div>
                              <div className="text-[9px] text-[#94a098]">events</div>
                            </div>
                          </div>
                          <button onClick={() => setSelectedLocation(location)} aria-label={`View ${location.name} details`} className="rounded-lg border border-[#e4ebe3] px-3 py-2 text-[11px] font-semibold text-[#60736a] hover:bg-[#f6f8f5]">
                            Details
                          </button>
                        </div>
                      );
                    })
                  ) : (
                    <EmptyState icon={MapPinned} title="No locations saved yet" detail="Click Add on map or select a point on the monitoring map." />
                  )}
                </div>
              </section>

              <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-5 shadow-card">
                <h2 className="text-sm font-semibold">Location details</h2>
                <p className="mt-1 text-[11px] text-[#8a9990]">Select a saved place to inspect its available data.</p>
                {selectedLocation ? (
                  <LocationDetails
                    location={selectedLocation}
                    currentUserId={user.id}
                    summary={locationSummaries[selectedLocation.id]}
                    subscription={subscriptions.find(s => s.location_id === selectedLocation.id)}
                    onRename={renameLocation}
                    onDelete={removeLocation}
                    onSaveSubscription={handleSaveSubscription}
                    onDeleteSubscription={handleDeleteSubscription}
                  />
                ) : (
                  <EmptyState icon={CircleHelp} title="Choose a location" detail="Shared places appear when their owner grants your account access." />
                )}
              </section>
            </div>
          )}

          {/* Section: Satellite Detections & Events */}
          {section === "Satellite Detections & Events" && (
            <div className="grid gap-5 xl:grid-cols-2">
              <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-5 shadow-card">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold">Satellite thermal anomalies</h2>
                    <p className="mt-1 text-[11px] text-[#8a9990]">Available within 5 km of your saved monitoring locations</p>
                  </div>
                  <span className="rounded-full bg-[#fff0e9] px-2.5 py-1 text-[10px] font-semibold text-[#be6543]">NASA FIRMS</span>
                </div>
                <div className="mt-4 divide-y divide-[#edf0eb]">
                  {observations.length ? (
                    observations.map(item => (
                      <div key={`${item.id}:${item.point.longitude}`} className="flex items-start gap-3 py-3">
                        <div className="mt-0.5 grid h-8 w-8 place-items-center rounded-lg bg-[#fff0e9] text-[#d76d47]">
                          <ThermometerSun className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-semibold">Thermal anomaly · {item.product}</div>
                          <div className="mt-1 text-[10px] text-[#84938a]">
                            {formatTime(item.observed_at)} · {item.point.latitude.toFixed(4)}, {item.point.longitude.toFixed(4)}
                          </div>
                          <div className="mt-1 text-[10px] text-[#65786d]">
                            {(item.distance_m / 1000).toFixed(2)} km · confidence {item.confidence || "not supplied"}
                            {item.frp ? ` · FRP ${item.frp} MW` : ""}
                          </div>
                        </div>
                        <button onClick={() => { selectObservation(item); setSection("Live Monitoring Map"); }} className="text-[10px] font-semibold text-[#176b58]">
                          Map
                        </button>
                      </div>
                    ))
                  ) : (
                    <EmptyState icon={ThermometerSun} title="No observations returned" detail="The backend returned no anomalies within the current 5 km query radius." />
                  )}
                </div>
              </section>

              <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-5 shadow-card">
                <div>
                  <h2 className="text-sm font-semibold">Geospatially associated events</h2>
                  <p className="mt-1 text-[11px] text-[#8a9990]">Event records derived from satellite observations</p>
                </div>
                <div className="mt-4 divide-y divide-[#edf0eb]">
                  {events.length ? (
                    events.map(item => (
                      <div key={item.id} className="flex items-start gap-3 py-3">
                        <div className="mt-0.5 grid h-8 w-8 place-items-center rounded-lg bg-[#f0ebff] text-[#7254cd]">
                          <Flame className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-semibold">Observed event · {item.status}</div>
                          <div className="mt-1 text-[10px] text-[#84938a]">Started {formatTime(item.started_at)}</div>
                          <div className="mt-1 text-[10px] text-[#65786d]">Record {shortId(item.id)} · satellite association</div>
                        </div>
                        {item.point && (
                          <button onClick={() => { selectEvent(item); setSection("Live Monitoring Map"); }} className="text-[10px] font-semibold text-[#176b58]">
                            Map
                          </button>
                        )}
                      </div>
                    ))
                  ) : (
                    <EmptyState icon={Flame} title="No event associations returned" detail="Associated event records appear when nearby satellite observations are grouped by the backend." />
                  )}
                </div>
              </section>
            </div>
          )}

          {/* Section: Alerts */}
          {section === "Alerts" && (
            <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-5 shadow-card">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold">Your alerts</h2>
                  <p className="mt-1 text-[11px] text-[#8a9990]">User-specific notifications from monitored locations</p>
                </div>
                <div className="rounded-full bg-[#eef4ee] px-3 py-1.5 text-[10px] font-semibold text-[#4d7860]">
                  {unreadCount} unread
                </div>
              </div>
              <div className="mt-4 divide-y divide-[#edf0eb]">
                {alerts.length ? (
                  alerts.map(alert => (
                    <article key={alert.id} className={`flex gap-3 py-4 ${alert.status === "unread" ? "" : "opacity-75"}`}>
                      <div className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl ${alert.alert_type === "satellite_thermal_anomaly" ? "bg-[#fff0e9] text-[#d76d47]" : "bg-[#edf3ed] text-[#557565]"}`}>
                        {alert.alert_type === "satellite_thermal_anomaly" ? <ThermometerSun className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-xs font-semibold">{alert.title}</h3>
                          {alert.status === "unread" && <span className="rounded-full bg-[#eaf4ed] px-2 py-0.5 text-[9px] font-semibold text-[#33734f]">New</span>}
                          <span className="rounded-full bg-[#f2f4f0] px-2 py-0.5 text-[9px] text-[#718078]">{alert.classification}</span>
                        </div>
                        <p className="mt-1.5 whitespace-pre-line text-[11px] leading-5 text-[#687a70]">{alert.message}</p>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[#89978e]">
                          <span>{formatTime(alert.created_at)}</span>
                          {alert.match.distance_m && <span>{(Number(alert.match.distance_m) / 1000).toFixed(2)} km from location</span>}
                          {alert.match.observation_id && <span>Observation {shortId(alert.match.observation_id)}</span>}
                        </div>
                      </div>
                      {alert.status === "unread" && (
                        <button onClick={() => void markRead(alert)} className="flex h-8 shrink-0 items-center gap-1 rounded-lg border border-[#dce8de] px-2.5 text-[10px] font-semibold text-[#3c7652] hover:bg-[#f1f7f2]">
                          <Check className="h-3.5 w-3.5" />
                          <span className="hidden sm:inline">Mark read</span>
                        </button>
                      )}
                    </article>
                  ))
                ) : (
                  <EmptyState icon={Bell} title="No alerts yet" detail="New user-specific alerts will appear here when the backend alert engine processes matching observations." />
                )}
              </div>
            </section>
          )}

          {/* Section: Hiking Routes Preview */}
          {section === "Hiking Routes" && (
            <RoutePreview
              api={api}
              locations={locations}
              onRouteCalculated={res => {
                setRouteResult(res);
                if (res) {
                  // Prompt user that preview is active on map
                }
              }}
            />
          )}

          {/* Section: Weather Context (Strictly Genuine) */}
          {section === "Weather" && (
            <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
              <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-6 shadow-card space-y-4">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#e8f1f7] text-[#4383a2]">
                  <Wind className="h-5 w-5" />
                </div>
                <h2 className="text-base font-semibold">Weather Evidence & Meteorological Context</h2>
                <p className="text-xs leading-6 text-[#75837b]">
                  POLARIS X adheres to strict scientific integrity. No synthetic, simulated, or live weather measurements
                  are rendered without genuine backend provider evidence.
                </p>

                {weatherEvidenceRecords.length > 0 ? (
                  <div className="space-y-3 pt-2">
                    <div className="text-xs font-semibold text-[#254d3d]">Evidence Attached to Your Alerts</div>
                    {weatherEvidenceRecords.map((rec, i) => (
                      <div key={i} className="rounded-xl border border-[#dde6dc] bg-[#f8faf7] p-3 text-xs space-y-1">
                        <div className="font-semibold text-[#1f4c3c]">{rec.alertTitle}</div>
                        <div className="text-[10px] text-[#788a80]">Attached at: {formatTime(rec.createdAt)}</div>
                        <div className="text-[11px] font-mono text-[#586e63]">
                          {JSON.stringify(rec.evidence, null, 2)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-[#e6ece6] bg-[#fafbf8] p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold text-[#5a7065]">
                      <CircleHelp className="h-4 w-4 text-[#829389]" />
                      No genuine weather readings returned
                    </div>
                    <p className="mt-2 text-[11px] leading-5 text-[#839087]">
                      No authenticated weather records are currently attached to your monitored alerts or locations.
                      To query meteorological context for a saved place, ask the AI Assistant below.
                    </p>
                    <button
                      onClick={() => setSection("AI Assistant")}
                      className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-[#176b58] hover:underline"
                    >
                      <MessageCircle className="h-3.5 w-3.5" />
                      Ask AI Assistant for Location Weather Context
                    </button>
                  </div>
                )}
              </section>

              <section className="space-y-3">
                <WeatherType
                  icon={Wind}
                  title="Operational Forecast"
                  detail="Forward-looking model context from Open-Meteo. It describes valid forecast windows, not immediate station telemetry."
                  tone="blue"
                />
                <WeatherType
                  icon={Activity}
                  title="Historical Reanalysis (ERA5)"
                  detail="Retrospective gridded atmospheric model analysis. It represents scientific reanalysis, not direct live conditions."
                  tone="violet"
                />
                <WeatherType
                  icon={ThermometerSun}
                  title="Direct Weather-Station Observations"
                  detail="Direct physical measurements are shown only when an authorized ground station data source is actively streaming."
                  tone="green"
                />
              </section>
            </div>
          )}

          {/* Section: AI Assistant */}
          {section === "AI Assistant" && (
            <div className="grid h-[min(720px,calc(100vh-190px))] min-h-[540px] gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
              <section className="flex flex-col rounded-[22px] border border-[#e5ebe4] bg-white p-4 shadow-card">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold">Conversations</h2>
                    <p className="mt-1 text-[10px] text-[#8a9990]">Private to your account</p>
                  </div>
                  <button aria-label="New conversation" onClick={() => void createConversation()} className="rounded-lg bg-[#176b58] p-2 text-white hover:bg-[#125646]">
                    <Plus className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-4 space-y-1 overflow-auto">
                  {chatConversations.map(conversation => (
                    <div key={conversation.id} className={`group flex items-center rounded-xl ${activeConversation?.id === conversation.id ? "bg-[#eaf4ed]" : "hover:bg-[#f6f8f5]"}`}>
                      <button onClick={() => void selectConversation(conversation)} className="min-w-0 flex-1 px-3 py-2.5 text-left">
                        <div className="truncate text-xs font-semibold">Conversation {shortId(conversation.id)}</div>
                        <div className="mt-1 text-[10px] text-[#8b9890]">{formatTime(conversation.started_at)}</div>
                      </button>
                      <button aria-label="Archive conversation" title="Archive" onClick={() => void archiveConversation(conversation)} className="mr-2 rounded-md p-1.5 text-[#9aa59e] opacity-0 hover:bg-white hover:text-[#bd6546] group-hover:opacity-100">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                  {!chatConversations.length && <p className="px-2 py-3 text-xs leading-5 text-[#8a9990]">Create a conversation to ask about data in your workspace.</p>}
                </div>
              </section>

              <section className="flex min-h-0 flex-col overflow-hidden rounded-[22px] border border-[#e5ebe4] bg-white shadow-card">
                <div className="flex items-center gap-3 border-b border-[#edf0eb] px-5 py-4">
                  <div className="grid h-9 w-9 place-items-center rounded-xl bg-[#e9f4ed] text-[#176b58]">
                    <Sparkles className="h-4 w-4" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold">POLARIS Assistant</h2>
                    <p className="mt-0.5 text-[10px] text-[#8a9990]">Uses authorized workspace tools · no browser key required</p>
                  </div>
                </div>
                <div className="flex-1 space-y-4 overflow-auto p-5">
                  {!activeConversation ? (
                    <div className="grid h-full place-items-center">
                      <div className="max-w-sm text-center">
                        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-[#e9f4ed] text-[#176b58]">
                          <MessageCircle className="h-6 w-6" />
                        </div>
                        <h3 className="mt-4 text-sm font-semibold">Ask about your monitoring data</h3>
                        <p className="mt-2 text-xs leading-5 text-[#819087]">Start a conversation to inspect saved locations, recent alerts, event associations, and available weather context.</p>
                        <button onClick={() => void createConversation()} className="mt-4 rounded-lg bg-[#176b58] px-4 py-2 text-xs font-semibold text-white">
                          Start conversation
                        </button>
                      </div>
                    </div>
                  ) : (
                    chatMessages.map(message => (
                      <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${message.role === "user" ? "rounded-br-md bg-[#176b58] text-white" : "rounded-bl-md bg-[#f1f5ef] text-[#243a31]"}`}>
                          <div className="whitespace-pre-wrap text-xs leading-5">{message.content}</div>
                          {message.role === "assistant" && message.tool_summaries.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {message.tool_summaries.map((tool, index) => (
                                <span key={`${tool.tool || tool.provider}-${index}`} className="rounded-full bg-white/80 px-2 py-0.5 text-[9px] text-[#61756a]">
                                  {tool.tool ? `${tool.tool.replaceAll("_", " ")} · ${tool.status}` : `Provider ${tool.provider}`}
                                </span>
                              ))}
                            </div>
                          )}
                          <div className={`mt-1.5 text-[9px] ${message.role === "user" ? "text-white/60" : "text-[#97a39b]"}`}>{formatTime(message.created_at)}</div>
                        </div>
                      </div>
                    ))
                  )}
                  {chatBusy && activeConversation && (
                    <div className="flex items-center gap-2 text-xs text-[#7c8d83]">
                      <LoaderCircle className="h-4 w-4 animate-spin" /> Working with your authorized data…
                    </div>
                  )}
                  {activeConversation && chatMessages.length === 0 && (
                    <div className="rounded-xl border border-[#e4ebe3] p-3 text-xs text-[#7d8c83]">Try “Show my locations” or “Do I have any recent alerts?”</div>
                  )}
                </div>
                <form onSubmit={sendChat} className="flex items-end gap-2 border-t border-[#edf0eb] p-4">
                  <textarea
                    aria-label="Message assistant"
                    rows={1}
                    value={chatText}
                    onChange={e => setChatText(e.target.value)}
                    disabled={!activeConversation || chatBusy}
                    placeholder="Ask about your locations, alerts or observations…"
                    className="max-h-28 min-h-11 flex-1 resize-y rounded-xl border border-[#dfe7df] px-3.5 py-3 text-xs outline-none focus:border-[#176b58] disabled:bg-[#f7f8f6]"
                  />
                  <button aria-label="Send message" disabled={!activeConversation || !chatText.trim() || chatBusy} className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#176b58] text-white hover:bg-[#125646] disabled:opacity-40">
                    <Send className="h-4 w-4" />
                  </button>
                </form>
                <div className="border-t border-[#f0f2ee] px-4 pb-3 text-[9px] text-[#9aa59e]">The assistant does not provide validated fire occurrence or spread predictions.</div>
              </section>
            </div>
          )}

          {/* Section: Account & Guidance */}
          {section === "Account / Guidance" && (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
              <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-6 shadow-card">
                <div className="flex items-center gap-4">
                  <div className="grid h-14 w-14 place-items-center rounded-2xl bg-[#e0efe4] text-lg font-bold text-[#176b58]">
                    {user.display_name.slice(0, 1).toUpperCase()}
                  </div>
                  <div>
                    <h2 className="text-base font-semibold">{user.display_name}</h2>
                    <p className="mt-1 text-xs text-[#84938a]">{user.email}</p>
                  </div>
                </div>
                <div className="mt-6 grid gap-3 sm:grid-cols-2">
                  <SettingValue label="Account ID" value={user.id} />
                  <SettingValue label="Role" value={user.roles.join(", ") || "user"} />
                  <SettingValue label="API Base URL" value={api.baseUrl} />
                  <SettingValue label="Session" value="Authenticated via JWT" />
                </div>
                <button onClick={onLogout} className="mt-6 flex items-center gap-2 rounded-xl border border-[#ecd8d0] px-4 py-2.5 text-xs font-semibold text-[#ad573b] hover:bg-[#fff7f4]">
                  <LogOut className="h-4 w-4" /> Sign out
                </button>
              </section>

              <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-6 shadow-card">
                <h2 className="text-sm font-semibold">Data Guidance & Scientific Attribution</h2>
                <div className="mt-4 space-y-3 text-xs leading-5 text-[#75837b]">
                  <p>
                    <strong>Satellite Radiometry:</strong> NASA FIRMS active fire products detect thermal anomalies based on middle and thermal infrared signals.
                  </p>
                  <p>
                    <strong>Not Validated Wildfires:</strong> Detections are unverified thermal signatures. Ground confirmation by local authorities is mandatory.
                  </p>
                  <p>
                    <strong>Routing Provider:</strong> Foot trail preview calculations are provided by OSRM or GraphHopper using OpenStreetMap network graphs.
                  </p>
                </div>
              </section>
            </div>
          )}

          <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-[#e7ece5] pt-4 text-[10px] text-[#9aa59e]">
            <span>POLARIS X · Public Wildfire Awareness Platform</span>
            <span>Thermal anomaly data supports awareness; it is not a confirmed emergency report.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function resultDistance(res: RoutePreviewResult) {
  if (res.distance_m < 1000) return `${Math.round(res.distance_m)} m`;
  return `${(res.distance_m / 1000).toFixed(1)} km`;
}

function MetricCard({
  icon: Icon,
  label,
  value,
  tone,
  note,
  onClick,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  tone: string;
  note: string;
  onClick: () => void;
}) {
  const tones: Record<string, string> = {
    green: "bg-[#e7f2eb] text-[#31825a]",
    orange: "bg-[#fff0e9] text-[#cf714d]",
    purple: "bg-[#f0ebff] text-[#7355cf]",
    blue: "bg-[#e8f1f7] text-[#4c89a5]",
  };
  return (
    <button
      onClick={onClick}
      className="rounded-[19px] border border-[#e5ebe4] bg-white p-4 text-left shadow-card transition hover:-translate-y-0.5 hover:shadow-lg"
    >
      <div className="flex items-start justify-between">
        <div className={`grid h-10 w-10 place-items-center rounded-xl ${tones[tone]}`}>
          <Icon className="h-[18px] w-[18px]" />
        </div>
        <ArrowUpRight className="h-4 w-4 text-[#b2bcb5]" />
      </div>
      <div className="mt-3 flex items-end gap-2">
        <div className="text-[27px] font-semibold leading-none tracking-tight">{value}</div>
        <div className="pb-0.5 text-xs font-medium text-[#5e7167]">{label}</div>
      </div>
      <div className="mt-2 text-[10px] text-[#97a39b]">{note}</div>
    </button>
  );
}

function EmptyState({ icon: Icon, title, detail }: { icon: typeof Activity; title: string; detail: string }) {
  return (
    <div className="flex flex-col items-center justify-center px-5 py-10 text-center">
      <div className="grid h-11 w-11 place-items-center rounded-xl bg-[#f2f5f1] text-[#82938a]">
        <Icon className="h-5 w-5" />
      </div>
      <div className="mt-3 text-xs font-semibold">{title}</div>
      <p className="mt-1 max-w-xs text-[10px] leading-4 text-[#929e96]">{detail}</p>
    </div>
  );
}

function LocationDetails({
  location,
  currentUserId,
  summary,
  subscription,
  onRename,
  onDelete,
  onSaveSubscription,
  onDeleteSubscription,
}: {
  location: Location;
  currentUserId: string;
  summary?: { recent_observations_count: number; associated_events_count: number; total_alerts: number; unread_alerts: number };
  subscription?: MonitoringSubscription;
  onRename: (location: Location, name: string) => void;
  onDelete: (location: Location) => void;
  onSaveSubscription: (locationId: string, radius_m: number, minimum_severity: string, enabled: boolean) => void;
  onDeleteSubscription: (subscriptionId: string) => void;
}) {
  const [name, setName] = useState(location.name);
  const [radiusKm, setRadiusKm] = useState(subscription ? (subscription.radius_m / 1000).toString() : "5");
  const [severity, setSeverity] = useState<string>(subscription ? subscription.minimum_severity : "low");
  const [enabled, setEnabled] = useState(subscription ? subscription.enabled : true);

  useEffect(() => setName(location.name), [location.name]);
  useEffect(() => {
    if (subscription) {
      setRadiusKm((subscription.radius_m / 1000).toString());
      setSeverity(subscription.minimum_severity);
      setEnabled(subscription.enabled);
    } else {
      setRadiusKm("5");
      setSeverity("low");
      setEnabled(true);
    }
  }, [subscription]);

  return (
    <div className="mt-5">
      <div className="rounded-xl bg-[#f7f9f5] p-4">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-[#89978e]">Location</div>
        <div className="mt-2 text-sm font-semibold">{location.name}</div>
        <div className="mt-1 text-xs text-[#819087]">{location.location_type}</div>
        <div className="mt-3 text-[11px] text-[#63766b]">
          {location.point.latitude.toFixed(5)}, {location.point.longitude.toFixed(5)}
        </div>
        {location.description && <p className="mt-2 text-xs text-[#84938a]">{location.description}</p>}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        {[
          ["Recent detections", summary?.recent_observations_count],
          ["Associated events", summary?.associated_events_count],
          ["Alerts", summary?.total_alerts],
          ["Unread", summary?.unread_alerts],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-[#edf0eb] p-3">
            <div className="text-lg font-semibold">{value ?? "—"}</div>
            <div className="mt-0.5 text-[10px] text-[#87958d]">{label}</div>
          </div>
        ))}
      </div>

      {/* Subscription configuration */}
      <div className="mt-4 rounded-xl border border-[#dfe8df] bg-[#f8faf7] p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-[#176b58]" />
            <span className="text-xs font-semibold">Alert Subscription</span>
          </div>
          {subscription ? (
            <span
              className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${
                subscription.enabled ? "bg-[#eaf4ed] text-[#33734f]" : "bg-[#f4efe8] text-[#916a44]"
              }`}
            >
              {subscription.enabled ? "Active" : "Paused"}
            </span>
          ) : (
            <span className="rounded-full bg-[#f0f2ef] px-2 py-0.5 text-[9px] text-[#718078]">Not configured</span>
          )}
        </div>

        <div className="mt-3 space-y-3">
          <div>
            <label className="block text-[10px] font-semibold text-[#6d7f74]">Monitoring radius (km)</label>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="number"
                min="0.5"
                max="100"
                step="0.5"
                value={radiusKm}
                onChange={e => setRadiusKm(e.target.value)}
                aria-label="Monitoring radius in km"
                className="w-24 rounded-lg border border-[#d9e3d9] bg-white px-2.5 py-1.5 text-xs outline-none focus:border-[#176b58]"
              />
              <span className="text-xs text-[#829288]">km ({(Number(radiusKm) * 1000 || 0).toLocaleString()} m)</span>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-semibold text-[#6d7f74]">Minimum alert severity</label>
            <select
              value={severity}
              onChange={e => setSeverity(e.target.value)}
              aria-label="Minimum alert severity"
              className="mt-1 w-full rounded-lg border border-[#d9e3d9] bg-white px-2.5 py-1.5 text-xs outline-none focus:border-[#176b58]"
            >
              <option value="low">Low (all informational thermal anomalies)</option>
              <option value="moderate">Moderate</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-xs text-[#52665b]">
            <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} className="rounded text-[#176b58]" />
            <span>Enable alerts for this location</span>
          </label>

          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => onSaveSubscription(location.id, Math.round(Number(radiusKm) * 1000), severity, enabled)}
              disabled={!radiusKm || Number(radiusKm) <= 0 || Number(radiusKm) > 100}
              className="rounded-lg bg-[#176b58] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#125646] disabled:opacity-40"
            >
              {subscription ? "Update subscription" : "Configure monitoring"}
            </button>
            {subscription && (
              <button
                onClick={() => onDeleteSubscription(subscription.id)}
                className="rounded-lg border border-[#ecd5cc] px-2.5 py-1.5 text-[11px] font-semibold text-[#ad5438] hover:bg-[#fff5f1]"
              >
                Remove
              </button>
            )}
          </div>
        </div>
      </div>

      {location.owner_id === currentUserId && (
        <div className="mt-4 border-t border-[#edf0eb] pt-4">
          <label className="block text-[10px] font-semibold text-[#74837a]">Rename location</label>
          <div className="mt-1.5 flex gap-2">
            <input
              aria-label="Rename location"
              value={name}
              onChange={e => setName(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-[#e0e7e0] px-2.5 py-2 text-xs outline-none focus:border-[#176b58]"
            />
            <button
              onClick={() => onRename(location, name)}
              disabled={!name.trim() || name === location.name}
              className="rounded-lg bg-[#176b58] px-3 text-[10px] font-semibold text-white disabled:opacity-40"
            >
              Save
            </button>
          </div>
          <button onClick={() => onDelete(location)} className="mt-3 flex items-center gap-1.5 text-[10px] font-semibold text-[#b65a3c]">
            <Trash2 className="h-3.5 w-3.5" /> Remove location
          </button>
        </div>
      )}
    </div>
  );
}

function WeatherType({ icon: Icon, title, detail, tone }: { icon: typeof Activity; title: string; detail: string; tone: string }) {
  const colors: Record<string, string> = {
    blue: "bg-[#e8f1f7] text-[#4383a2]",
    violet: "bg-[#f0ebff] text-[#7254cd]",
    green: "bg-[#e8f3eb] text-[#4c8a62]",
  };
  return (
    <div className="flex gap-3 rounded-[18px] border border-[#e5ebe4] bg-white p-4 shadow-card">
      <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${colors[tone]}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <div className="text-xs font-semibold">{title}</div>
        <p className="mt-1 text-[11px] leading-5 text-[#839087]">{detail}</p>
      </div>
    </div>
  );
}

function SettingValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[#f7f9f5] p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#94a097]">{label}</div>
      <div className="mt-1 break-all text-xs font-medium text-[#52665b]">{value}</div>
    </div>
  );
}
