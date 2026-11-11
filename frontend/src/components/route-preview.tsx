"use client";

import { FormEvent, useState } from "react";
import { Compass, Footprints, Info, LoaderCircle, Navigation, Route } from "lucide-react";
import { Location, PolarisApi, RoutePreviewResult } from "@/lib/api";

type Props = {
  api: PolarisApi;
  locations: Location[];
  onRouteCalculated: (result: RoutePreviewResult | null) => void;
};

export function RoutePreview({ api, locations, onRouteCalculated }: Props) {
  const [originType, setOriginType] = useState<"location" | "manual">("location");
  const [destType, setDestType] = useState<"location" | "manual">("manual");
  const [originLocationId, setOriginLocationId] = useState<string>(locations[0]?.id || "");
  const [destLocationId, setDestLocationId] = useState<string>(locations[1]?.id || locations[0]?.id || "");

  const [originCoords, setOriginCoords] = useState({ lat: "33.9000", lon: "-6.8000" });
  const [destCoords, setDestCoords] = useState({ lat: "33.9500", lon: "-6.8500" });

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RoutePreviewResult | null>(null);

  const calculateRoute = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");

    try {
      let originPt: { longitude: number; latitude: number };
      if (originType === "location") {
        const loc = locations.find(l => l.id === originLocationId);
        if (!loc) throw new Error("Please select a valid origin location.");
        originPt = loc.point;
      } else {
        const lat = parseFloat(originCoords.lat);
        const lon = parseFloat(originCoords.lon);
        if (isNaN(lat) || isNaN(lon)) throw new Error("Invalid origin coordinates.");
        originPt = { latitude: lat, longitude: lon };
      }

      let destPt: { longitude: number; latitude: number };
      if (destType === "location") {
        const loc = locations.find(l => l.id === destLocationId);
        if (!loc) throw new Error("Please select a valid destination location.");
        destPt = loc.point;
      } else {
        const lat = parseFloat(destCoords.lat);
        const lon = parseFloat(destCoords.lon);
        if (isNaN(lat) || isNaN(lon)) throw new Error("Invalid destination coordinates.");
        destPt = { latitude: lat, longitude: lon };
      }

      const preview = await api.previewRoute({
        origin: originPt,
        destination: destPt,
        profile: "foot",
      });

      setResult(preview);
      onRouteCalculated(preview);
    } catch (reason) {
      const msg = (reason as Error).message || "Could not calculate route preview.";
      setError(msg);
      setResult(null);
      onRouteCalculated(null);
    } finally {
      setBusy(false);
    }
  };

  const clearRoute = () => {
    setResult(null);
    setError("");
    onRouteCalculated(null);
  };

  const formatDistance = (meters: number) => {
    if (meters < 1000) return `${Math.round(meters)} m`;
    return `${(meters / 1000).toFixed(2)} km`;
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.round(seconds / 60);
    if (mins < 60) return `${mins} min`;
    const hrs = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hrs} hr ${remMins} min`;
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="rounded-[22px] border border-[#e5ebe4] bg-white p-6 shadow-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#e9f4ed] text-[#176b58]">
              <Footprints className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold">Hiking & Field Route Preview</h2>
              <p className="mt-0.5 text-xs text-[#8a9990]">
                Factual foot path preview using the backend routing provider
              </p>
            </div>
          </div>
          <span className="rounded-full bg-[#f0f4ef] px-3 py-1 text-[10px] font-semibold text-[#5a7867]">
            Profile: Foot / Hiking
          </span>
        </div>

        <div className="mt-4 rounded-xl border border-[#dfe8df] bg-[#f9faf7] p-3.5 text-xs text-[#63766c]">
          <div className="flex items-center gap-2 font-semibold text-[#176b58]">
            <Info className="h-4 w-4 shrink-0" />
            <span>Temporary Route Awareness</span>
          </div>
          <p className="mt-1 leading-5 text-[11px] text-[#718278]">
            Route previews are temporary calculations for field planning and situational awareness.
            Route saving and alert subscriptions on hiking corridors are deferred until a subsequent release.
          </p>
        </div>

        {error && (
          <div role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs text-red-700">
            {error}
          </div>
        )}

        <form onSubmit={calculateRoute} className="mt-6 space-y-5">
          {/* Origin selector */}
          <div className="rounded-xl border border-[#edf1ea] p-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[#42554a]">Origin Point</label>
              <div className="flex rounded-lg border border-[#dde4dc] bg-white p-0.5 text-[10px]">
                <button
                  type="button"
                  onClick={() => setOriginType("location")}
                  className={`rounded px-2.5 py-1 font-medium ${originType === "location" ? "bg-[#176b58] text-white" : "text-[#718278]"}`}
                >
                  Saved Place
                </button>
                <button
                  type="button"
                  onClick={() => setOriginType("manual")}
                  className={`rounded px-2.5 py-1 font-medium ${originType === "manual" ? "bg-[#176b58] text-white" : "text-[#718278]"}`}
                >
                  Coordinates
                </button>
              </div>
            </div>

            {originType === "location" ? (
              <select
                aria-label="Origin saved place"
                value={originLocationId}
                onChange={e => setOriginLocationId(e.target.value)}
                className="mt-2.5 w-full rounded-lg border border-[#dde5dc] bg-white px-3 py-2 text-xs outline-none focus:border-[#176b58]"
              >
                {locations.length === 0 && <option value="">No saved locations available</option>}
                {locations.map(loc => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name} ({loc.point.latitude.toFixed(4)}, {loc.point.longitude.toFixed(4)})
                  </option>
                ))}
              </select>
            ) : (
              <div className="mt-2.5 grid grid-cols-2 gap-2">
                <input
                  aria-label="Origin latitude"
                  type="number"
                  step="0.0001"
                  required
                  value={originCoords.lat}
                  onChange={e => setOriginCoords({ ...originCoords, lat: e.target.value })}
                  placeholder="Latitude (e.g. 33.90)"
                  className="rounded-lg border border-[#dde5dc] bg-white px-3 py-2 text-xs outline-none focus:border-[#176b58]"
                />
                <input
                  aria-label="Origin longitude"
                  type="number"
                  step="0.0001"
                  required
                  value={originCoords.lon}
                  onChange={e => setOriginCoords({ ...originCoords, lon: e.target.value })}
                  placeholder="Longitude (e.g. -6.80)"
                  className="rounded-lg border border-[#dde5dc] bg-white px-3 py-2 text-xs outline-none focus:border-[#176b58]"
                />
              </div>
            )}
          </div>

          {/* Destination selector */}
          <div className="rounded-xl border border-[#edf1ea] p-4">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[#42554a]">Destination Point</label>
              <div className="flex rounded-lg border border-[#dde4dc] bg-white p-0.5 text-[10px]">
                <button
                  type="button"
                  onClick={() => setDestType("location")}
                  className={`rounded px-2.5 py-1 font-medium ${destType === "location" ? "bg-[#176b58] text-white" : "text-[#718278]"}`}
                >
                  Saved Place
                </button>
                <button
                  type="button"
                  onClick={() => setDestType("manual")}
                  className={`rounded px-2.5 py-1 font-medium ${destType === "manual" ? "bg-[#176b58] text-white" : "text-[#718278]"}`}
                >
                  Coordinates
                </button>
              </div>
            </div>

            {destType === "location" ? (
              <select
                aria-label="Destination saved place"
                value={destLocationId}
                onChange={e => setDestLocationId(e.target.value)}
                className="mt-2.5 w-full rounded-lg border border-[#dde5dc] bg-white px-3 py-2 text-xs outline-none focus:border-[#176b58]"
              >
                {locations.length === 0 && <option value="">No saved locations available</option>}
                {locations.map(loc => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name} ({loc.point.latitude.toFixed(4)}, {loc.point.longitude.toFixed(4)})
                  </option>
                ))}
              </select>
            ) : (
              <div className="mt-2.5 grid grid-cols-2 gap-2">
                <input
                  aria-label="Destination latitude"
                  type="number"
                  step="0.0001"
                  required
                  value={destCoords.lat}
                  onChange={e => setDestCoords({ ...destCoords, lat: e.target.value })}
                  placeholder="Latitude (e.g. 33.95)"
                  className="rounded-lg border border-[#dde5dc] bg-white px-3 py-2 text-xs outline-none focus:border-[#176b58]"
                />
                <input
                  aria-label="Destination longitude"
                  type="number"
                  step="0.0001"
                  required
                  value={destCoords.lon}
                  onChange={e => setDestCoords({ ...destCoords, lon: e.target.value })}
                  placeholder="Longitude (e.g. -6.85)"
                  className="rounded-lg border border-[#dde5dc] bg-white px-3 py-2 text-xs outline-none focus:border-[#176b58]"
                />
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="flex items-center gap-2 rounded-xl bg-[#176b58] px-5 py-3 text-xs font-semibold text-white hover:bg-[#125646] disabled:opacity-60"
            >
              {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Navigation className="h-4 w-4" />}
              {busy ? "Calculating Route…" : "Calculate Route Preview"}
            </button>
            {result && (
              <button
                type="button"
                onClick={clearRoute}
                className="rounded-xl border border-[#dde5dc] px-4 py-3 text-xs font-semibold text-[#667a6e] hover:bg-[#f6f8f5]"
              >
                Clear Preview
              </button>
            )}
          </div>
        </form>
      </section>

      {/* Results panel */}
      <section className="flex flex-col rounded-[22px] border border-[#e5ebe4] bg-white p-5 shadow-card">
        <h3 className="text-sm font-semibold">Route Summary</h3>
        <p className="mt-0.5 text-[11px] text-[#8a9990]">
          Calculated by provider and overlayed on the monitoring map
        </p>

        {result ? (
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl bg-[#f7f9f5] p-3 text-center">
                <div className="text-[10px] uppercase tracking-wider text-[#8a9990]">Distance</div>
                <div className="mt-1 text-lg font-bold text-[#176b58]">{formatDistance(result.distance_m)}</div>
              </div>
              <div className="rounded-xl bg-[#f7f9f5] p-3 text-center">
                <div className="text-[10px] uppercase tracking-wider text-[#8a9990]">Est. Walking Time</div>
                <div className="mt-1 text-lg font-bold text-[#176b58]">{formatDuration(result.duration_s)}</div>
              </div>
            </div>

            <div className="rounded-xl border border-[#edf0eb] p-3.5 text-xs text-[#52645a] space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[#84948a]">Routing Engine</span>
                <span className="font-semibold uppercase">{result.provider}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#84948a]">Travel Profile</span>
                <span className="font-semibold">{result.profile}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#84948a]">Waypoints</span>
                <span className="font-semibold">{result.waypoints?.length || 2} points</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#84948a]">Storage Status</span>
                <span className="font-semibold text-amber-700">Preview Only (Unsaved)</span>
              </div>
            </div>

            <div className="rounded-xl bg-[#fffaf5] border border-[#fae8d8] p-3 text-[11px] leading-5 text-[#91582e]">
              <div className="font-semibold flex items-center gap-1.5">
                <Compass className="h-3.5 w-3.5" />
                Wildfire Safety Guidance
              </div>
              <p className="mt-1">
                This preview plots path distance and terrain time. Thermal anomaly records within 5 km of your path
                are visible on the Live Monitoring Map. It does not replace local emergency alerts.
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-xs text-[#89998f]">
            <Route className="h-10 w-10 text-[#c8d4c8] mb-2" />
            <p>Select origin and destination to calculate a hiking route preview.</p>
          </div>
        )}
      </section>
    </div>
  );
}
