import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import MapView from "./map-view";

vi.mock("maplibre-gl", () => {
  class MockMap { on() { return this; } addControl() { return this; } remove() {} flyTo() {} fitBounds() {} }
  class MockMarker { element: HTMLElement; constructor(options: { element: HTMLElement }) { this.element = options.element; } setLngLat() { return this; } setPopup() { return this; } addTo() { document.body.append(this.element); return this; } remove() { this.element.remove(); } }
  class MockPopup { setDOMContent() { return this; } }
  class Bounds { extend() { return this; } }
  return { Map: MockMap, Marker: MockMarker, Popup: MockPopup, NavigationControl: class {}, ScaleControl: class {}, GeolocateControl: class {}, LngLatBounds: Bounds };
});

describe("MapView", () => {
  afterEach(() => { document.querySelectorAll(".map-pin").forEach(node => node.remove()); });
  it("renders distinct markers for real locations and satellite observations", async () => {
    render(<MapView locations={[{ id: "loc", owner_id: "u", name: "North Farm", location_type: "farm", description: null, point: { longitude: -6.8, latitude: 33.9 } }]} observations={[{ id: "obs", external_id: "FIRMS-42", product: "VIIRS", observed_at: "2026-11-10T09:00:00Z", confidence: "nominal", frp: null, brightness_temperature: null, point: { longitude: -6.81, latitude: 33.91 }, distance_m: 1000 }]} events={[]} selectedPoint={null} onMapClick={() => {}} onSelectLocation={() => {}} onSelectObservation={() => {}} onSelectEvent={() => {}} />);
    expect(await screen.findByLabelText("Monitoring location: North Farm")).toBeInTheDocument();
    expect(screen.getByLabelText("Satellite thermal anomaly: FIRMS-42")).toBeInTheDocument();
  });
});
