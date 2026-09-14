import { type ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TankRead } from "../lib/apiTypes";
import type { LiveReading } from "../store/telemetry";

vi.mock("@react-three/fiber", () => ({
  Canvas: vi.fn(() => <div data-testid="r3f-canvas" />),
  useFrame: () => {},
}));

vi.mock("@react-three/drei", () => ({
  OrbitControls: () => null,
  Html: ({ children }: { children?: ReactNode }) => (
    <div data-testid="drei-html">{children}</div>
  ),
}));

import { tankSceneConfig } from "../components/tanks/TankCanvas3D";
import TankCanvas3D from "../components/tanks/TankCanvas3D";

vi.mock("../api/client", () => ({
  api: {
    getTank: vi.fn(),
    listFuelTypes: vi.fn(),
    tankAlarms: vi.fn(),
    rangeReadings: vi.fn(),
    ackAlarm: vi.fn(),
  },
}));
import { api } from "../api/client";

vi.mock("../hooks/useTelemetry", () => ({
  useTelemetry: () => ({
    live: null,
    recent: [],
    latest: null,
    loading: false,
  }),
}));

vi.mock("../components/charts/TelemetryChart", () => ({
  TelemetryChart: () => <div data-testid="mock-telemetry-chart" />,
}));

vi.mock("../components/tanks/TankCanvas", () => ({
  TankCanvas: () => <div data-testid="mock-tank-canvas" />,
}));

vi.mock("../components/tanks/StrappingCard", () => ({
  default: () => <div data-testid="mock-strapping-card" />,
}));

import TankDetail from "./TankDetail";
import { Canvas } from "@react-three/fiber";

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/tanks/t1"]}>
        <Routes>
          <Route path="/tanks/:tankId" element={<TankDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const defaultTank: TankRead = {
  id: "t1",
  name: "Alpha",
  site_id: "s1",
  sensor_serial_number: "SN1",
  device_address: 1,
  tank_orientation: "vertical",
  tank_diameter: 3,
  tank_height: 10,
  tank_length: null,
  tank_volume: 100,
  tank_shape: "vertical_cylinder",
  fuel_type_id: "f1",
  dish_depth: null,
  tank_width: null,
  strapping_table_id: null,
  elevation: null,
  calibration_factor: 1,
  atmospheric_pressure: 101325,
  low_level_threshold: null,
  critical_level_threshold: null,
  high_level_threshold: null,
  low_volume_threshold: null,
  high_volume_threshold: null,
  is_active: true,
  gateway_mac: null,
  created_at: "2026-01-01T00:00:00Z",
  connection_status: "online",
  last_connection: null,
};

function makeTank(overrides: Partial<TankRead> = {}): TankRead {
  return { ...defaultTank, ...overrides };
}

function makeLive(overrides: Partial<LiveReading> = {}): LiveReading {
  return {
    tank_id: "t1",
    timestamp: "2026-09-09T10:00:00Z",
    pressure: null,
    temperature: null,
    level: 3,
    volume: null,
    flow_rate: 0,
    fill_percent: 0.3,
    is_outlier: false,
    ...overrides,
  };
}

const tank = makeTank();

describe("TankDetail", () => {
  beforeEach(() => {
    vi.mocked(api.getTank).mockResolvedValue(tank);
    vi.mocked(api.listFuelTypes).mockResolvedValue([]);
    vi.mocked(api.tankAlarms).mockResolvedValue([]);
    vi.mocked(api.rangeReadings).mockResolvedValue([]);
  });

  it("renders the tank telemetry heading", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", {
        level: 3,
        name: /Alpha · Telemetry/,
      }),
    ).toBeInTheDocument();
  });

  it("renders a skeleton while the tank is loading", () => {
    vi.mocked(api.getTank).mockReturnValue(new Promise(() => {}) as never);
    const { container } = renderPage();
    expect(container.querySelector(".animate-pulse")).not.toBeNull();
  });

  it("renders an error card when the tank fails to load", async () => {
    vi.mocked(api.getTank).mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Failed to load tank.",
    );
  });
});

describe("TankCanvas3D", () => {
  const live = makeLive();

  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(Canvas).mockImplementation(() => (
      <div data-testid="r3f-canvas" />
    ));
  });

  it("derives fill fraction and threshold markers from tankGeometry (vertical cylinder)", () => {
    const cfg = tankSceneConfig(
      makeTank({
        tank_height: 10,
        high_level_threshold: 8,
        low_level_threshold: 2,
        critical_level_threshold: 9,
      }),
      live,
      [],
    );
    expect(cfg.fillFraction).toBeCloseTo(0.3);
    expect(cfg.thresholds.map((t) => t.label)).toEqual(["high", "low", "crit"]);
    expect(
      cfg.thresholds.find((t) => t.label === "high")?.fraction,
    ).toBeCloseTo(0.8);
    expect(cfg.thresholds.find((t) => t.label === "low")?.fraction).toBeCloseTo(
      0.2,
    );
    expect(
      cfg.thresholds.find((t) => t.label === "crit")?.fraction,
    ).toBeCloseTo(0.9);
  });

  it("derives fill fraction for a rectangular tank", () => {
    const cfg = tankSceneConfig(
      makeTank({
        tank_shape: "rectangular",
        tank_height: 8,
        tank_width: 4,
        tank_length: 5,
      }),
      makeLive({ level: 2, fill_percent: 0.25, flow_rate: 0 }),
      [],
    );
    expect(cfg.fillFraction).toBeCloseTo(0.25);
  });

  it("mounts an R3F canvas when WebGL is available", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as never,
    );
    const { getByTestId } = render(
      <TankCanvas3D tank={makeTank()} live={live} />,
    );
    expect(getByTestId("r3f-canvas")).toBeInTheDocument();
  });

  it("falls back to the 2D TankCanvas when WebGL is unavailable", () => {
    const { queryByTestId } = render(
      <TankCanvas3D tank={makeTank()} live={live} />,
    );
    expect(queryByTestId("mock-tank-canvas")).not.toBeNull();
    expect(queryByTestId("r3f-canvas")).toBeNull();
  });

  it("degrades to the 2D canvas when the WebGL renderer throws during mount", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as never,
    );
    vi.mocked(Canvas).mockImplementation(() => {
      throw new Error("renderer failed");
    });
    const { queryByTestId } = render(
      <TankCanvas3D tank={makeTank()} live={live} />,
    );
    expect(queryByTestId("mock-tank-canvas")).not.toBeNull();
    expect(queryByTestId("r3f-canvas")).toBeNull();
  });
});
