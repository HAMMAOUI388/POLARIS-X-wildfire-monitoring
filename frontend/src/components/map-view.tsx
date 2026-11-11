"use client";

import { useEffect, useRef } from "react";
import {
  GeolocateControl,
  LngLatBounds,
  Map as MapLibreMap,
  type MapMouseEvent,
  Marker,
  NavigationControl,
  Popup,
  ScaleControl,
} from "maplibre-gl";
import type { Location, Observation } from "@/lib/api";

export type EventPin = { id: string; status: string; started_at: string; point?: { longitude: number; latitude: number } };
export type SelectedPoint = { longitude: number; latitude: number };

type Props = {
  locations: Location[];
  observations: Observation[];
  events: EventPin[];
  selectedPoint: SelectedPoint | null;
  routeGeometry?: { type: string; coordinates: [number, number][] } | null;
  routeWaypoints?: SelectedPoint[];
  onMapClick?: (point: SelectedPoint) => void;
  onSelectLocation?: (location: Location) => void;
  onSelectObservation?: (observation: Observation) => void;
  onSelectEvent?: (event: EventPin) => void;
};

function popup(title: string, rows: string[]) {
  const node = document.createElement("div");
  node.className = "map-popup";
  const heading = document.createElement("strong"); heading.textContent = title; node.append(heading);
  for (const row of rows) { const line = document.createElement("div"); line.textContent = row; node.append(line); }
  return node;
}

export default function MapView({
  locations,
  observations,
  events,
  selectedPoint,
  routeGeometry,
  routeWaypoints,
  onMapClick,
  onSelectLocation,
  onSelectObservation,
  onSelectEvent,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const clickHandler = useRef(onMapClick); clickHandler.current = onMapClick;

  useEffect(() => {
    if (!container.current || map.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      center: [-6.9, 31.8],
      zoom: 5,
      minZoom: 2,
      style: { version: 8, sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } }, layers: [{ id: "osm", type: "raster", source: "osm", minzoom: 0, maxzoom: 19 }] },
    });
    instance.addControl(new NavigationControl({ visualizePitch: false }), "top-right");
    instance.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    instance.addControl(new GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false }), "top-right");
    instance.on("click", (event: MapMouseEvent) => {
      if (clickHandler.current) clickHandler.current({ longitude: event.lngLat.lng, latitude: event.lngLat.lat });
    });
    map.current = instance;
    return () => { markers.current.forEach(marker => marker.remove()); markers.current = []; instance.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    markers.current.forEach(marker => marker.remove()); markers.current = [];
    const addMarker = (element: HTMLElement, point: SelectedPoint, title: string, rows: string[], click?: () => void) => {
      const marker = new Marker({ element, anchor: "center" }).setLngLat([point.longitude, point.latitude]).setPopup(new Popup({ offset: 14, closeButton: true }).setDOMContent(popup(title, rows))).addTo(instance);
      if (click) element.addEventListener("click", click);
      markers.current.push(marker);
    };
    locations.forEach(item => { const pin = document.createElement("button"); pin.className = "map-pin location"; pin.setAttribute("aria-label", `Monitoring location: ${item.name}`); addMarker(pin, item.point, item.name, [item.location_type, `${item.point.latitude.toFixed(4)}, ${item.point.longitude.toFixed(4)}`], onSelectLocation ? () => onSelectLocation(item) : undefined); });
    observations.forEach(item => { const pin = document.createElement("button"); pin.className = "map-pin observation"; pin.setAttribute("aria-label", `Satellite thermal anomaly: ${item.external_id}`); addMarker(pin, item.point, "Satellite thermal anomaly", [`Source: NASA FIRMS · ${item.product}`, `Observed: ${new Date(item.observed_at).toLocaleString()}`, `Distance: ${(item.distance_m / 1000).toFixed(1)} km`, `Confidence: ${item.confidence || "Not provided"}`], onSelectObservation ? () => onSelectObservation(item) : undefined); });
    events.filter(item => item.point).forEach(item => { const pin = document.createElement("button"); pin.className = "map-pin event"; pin.setAttribute("aria-label", `Associated event ${item.id}`); addMarker(pin, item.point!, "Observed satellite-associated event", [`Status: ${item.status}`, `Started: ${new Date(item.started_at).toLocaleString()}`, "Not a confirmed wildfire"], onSelectEvent ? () => onSelectEvent(item) : undefined); });
    if (selectedPoint) { const pin = document.createElement("button"); pin.className = "map-pin location"; pin.style.background = "#2b90c8"; pin.setAttribute("aria-label", "Selected point to save"); addMarker(pin, selectedPoint, "Selected map point", [`${selectedPoint.latitude.toFixed(5)}, ${selectedPoint.longitude.toFixed(5)}`, "Save this point as a monitoring location"]); }

    if (routeWaypoints && routeWaypoints.length > 0) {
      routeWaypoints.forEach((wp, idx) => {
        const pin = document.createElement("button");
        pin.className = "map-pin location";
        pin.style.background = idx === 0 ? "#10b981" : idx === routeWaypoints.length - 1 ? "#ef4444" : "#3b82f6";
        pin.setAttribute("aria-label", `Route waypoint ${idx + 1}`);
        addMarker(pin, wp, idx === 0 ? "Route Origin" : idx === routeWaypoints.length - 1 ? "Route Destination" : `Waypoint ${idx}`, [`${wp.latitude.toFixed(5)}, ${wp.longitude.toFixed(5)}`]);
      });
    }

    const routeSourceId = "polaris-route-source";
    const routeLayerId = "polaris-route-line";
    if (typeof instance.getSource === "function" && typeof instance.addSource === "function") {
      try {
        if (typeof instance.getLayer === "function" && instance.getLayer(routeLayerId)) {
          instance.removeLayer(routeLayerId);
        }
        if (instance.getSource(routeSourceId)) {
          instance.removeSource(routeSourceId);
        }
        if (routeGeometry && "coordinates" in routeGeometry && Array.isArray(routeGeometry.coordinates) && routeGeometry.coordinates.length > 0) {
          instance.addSource(routeSourceId, {
            type: "geojson",
            data: {
              type: "Feature",
              properties: {},
              geometry: routeGeometry as any, // eslint-disable-line @typescript-eslint/no-explicit-any
            },
          });
          instance.addLayer({
            id: routeLayerId,
            type: "line",
            source: routeSourceId,
            layout: { "line-join": "round", "line-cap": "round" },
            paint: { "line-color": "#2563eb", "line-width": 4, "line-opacity": 0.85 },
          });
        }
      } catch { /* graceful fallback if map instance style is not ready */ }
    }

    const routeCoords: SelectedPoint[] = (routeGeometry && "coordinates" in routeGeometry && Array.isArray(routeGeometry.coordinates))
      ? routeGeometry.coordinates.map(([lng, lat]: [number, number]) => ({ longitude: lng, latitude: lat }))
      : [];

    const coords = [
      ...locations.map(item => item.point),
      ...observations.map(item => item.point),
      ...events.flatMap(item => item.point ? [item.point] : []),
      ...routeCoords,
    ];
    if (coords.length === 1) instance.flyTo({ center: [coords[0].longitude, coords[0].latitude], zoom: 9, duration: 600 });
    else if (coords.length > 1) {
      const bounds = new LngLatBounds(); coords.forEach(point => bounds.extend([point.longitude, point.latitude]));
      instance.fitBounds(bounds, { padding: 52, maxZoom: 9, duration: 600 });
    }
  }, [locations, observations, events, selectedPoint, routeGeometry, routeWaypoints, onSelectLocation, onSelectObservation, onSelectEvent]);

  return <div ref={container} data-testid="monitoring-map" className="h-full min-h-[420px] w-full overflow-hidden rounded-[22px]" />;
}
