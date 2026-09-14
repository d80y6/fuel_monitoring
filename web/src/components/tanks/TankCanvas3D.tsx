import { Component, type ReactNode } from "react";
import { Canvas } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import type { FuelType, TankRead } from "../../lib/apiTypes";
import type { LiveReading } from "../../store/telemetry";
import {
  fillFraction,
  fuelColor,
  type ShapeDims,
  type TankShape,
} from "../../lib/tankGeometry";
import { fuelCodeById } from "../../lib/fuelMap";
import { webglSupported } from "../../lib/webgl";
import { TankCanvas } from "./TankCanvas";

export interface ThreshMarker {
  fraction: number;
  color: string;
  label: string;
}

export interface TankSceneConfig {
  shape: TankShape;
  fillFraction: number;
  color: string;
  flow: number;
  thresholds: ThreshMarker[];
}

export function tankSceneConfig(
  tank: TankRead,
  live?: LiveReading,
  fuels: FuelType[] = [],
): TankSceneConfig {
  const shape = (tank.tank_shape ?? "vertical_cylinder") as TankShape;
  const dims: ShapeDims = {
    diameter: tank.tank_diameter,
    length: tank.tank_length,
    height: tank.tank_height,
    width: tank.tank_width,
    dishDepth: tank.dish_depth,
  };
  const level = live?.level ?? 0;
  const thresholds: ThreshMarker[] = [];
  for (const rec of [
    { v: tank.high_level_threshold, color: "#f87171", label: "high" },
    { v: tank.low_level_threshold, color: "#facc15", label: "low" },
    { v: tank.critical_level_threshold, color: "#ef4444", label: "crit" },
  ]) {
    if (rec.v != null) {
      thresholds.push({
        fraction: fillFraction(rec.v, shape, dims),
        color: rec.color,
        label: rec.label,
      });
    }
  }
  return {
    shape,
    fillFraction: fillFraction(level, shape, dims),
    color: fuelColor(fuelCodeById(fuels, tank.fuel_type_id)),
    flow: live?.flow_rate ?? 0,
    thresholds,
  };
}

function TankBody({ config }: { config: TankSceneConfig }) {
  switch (config.shape) {
    case "rectangular":
      return <boxGeometry args={[1.3, 1, 1.3]} />;
    case "spherical":
      return <sphereGeometry args={[0.9, 32, 32]} />;
    case "horizontal_cylinder":
    case "horizontal_elliptical_ends":
      return <cylinderGeometry args={[0.6, 0.6, 1.8, 32]} />;
    case "vertical_cylinder":
    case "custom_strapping":
    default:
      return <cylinderGeometry args={[1, 1, 1, 32]} />;
  }
}

function ThresholdMarker({
  marker,
  halfExtent,
}: {
  marker: ThreshMarker;
  halfExtent: number;
}) {
  return (
    <mesh position={[0, -halfExtent + marker.fraction * halfExtent * 2, 0]}>
      <boxGeometry args={[halfExtent * 3.4, 0.02, halfExtent * 3.4]} />
      <meshStandardMaterial color={marker.color} />
    </mesh>
  );
}

function TankScene({ config }: { config: TankSceneConfig }) {
  const target = config.fillFraction;
  const flow = config.flow;
  const isHorizontal =
    config.shape === "horizontal_cylinder" ||
    config.shape === "horizontal_elliptical_ends";
  // Cross-section half-extent of the tank's own vertical axis (world Y).
  // Vertical/side-shaped tanks span -0.5..0.5; horizontal tanks span -0.6..0.6.
  const halfExtent = isHorizontal ? 0.6 : 0.5;

  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[3, 5, 4]} intensity={0.9} />
      <OrbitControls
        enableDamping
        minDistance={3}
        maxDistance={14}
        maxPolarAngle={Math.PI * 0.9}
      />
      {/* Tank shell — rotated horizontally only for horizontal shapes. */}
      <mesh rotation={isHorizontal ? [0, 0, Math.PI / 2] : [0, 0, 0]}>
        <TankBody config={config} />
        <meshStandardMaterial
          color="#334155"
          metalness={0.3}
          roughness={0.5}
          transparent
          opacity={0.85}
        />
      </mesh>
      {/* Liquid always fills bottom-up along world Y (gravity), so it stays
          outside the shell's horizontal rotation. */}
      {isHorizontal ? (
        <mesh position={[0, -halfExtent + target * halfExtent, 0]}>
          <boxGeometry args={[1.5, target * halfExtent * 2, 0.9]} />
          <meshStandardMaterial
            color={config.color}
            transparent
            opacity={0.75}
          />
        </mesh>
      ) : (
        <mesh
          position={[0, -halfExtent + target * halfExtent, 0]}
          scale={[1, target, 1]}
        >
          <TankBody config={config} />
          <meshStandardMaterial
            color={config.color}
            transparent
            opacity={0.75}
          />
        </mesh>
      )}
      {config.thresholds.map((t) => (
        <ThresholdMarker key={t.label} marker={t} halfExtent={halfExtent} />
      ))}
      {flow !== 0 ? (
        <Html position={[0, 1.6, 0]} center>
          <div
            style={{ color: flow > 0 ? "#16a34a" : "#dc2626", fontWeight: 600 }}
          >
            {flow > 0 ? "▲ in" : "▼ out"}
          </div>
        </Html>
      ) : null}
    </>
  );
}

class SceneErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { hasError: boolean }
> {
  state: { hasError: boolean } = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}

interface TankCanvas3DProps {
  tank: TankRead;
  live?: LiveReading;
  fuels?: FuelType[];
}

export default function TankCanvas3D({
  tank,
  live,
  fuels = [],
}: TankCanvas3DProps) {
  const config = tankSceneConfig(tank, live, fuels);
  if (!webglSupported()) {
    return <TankCanvas tank={tank} live={live} fuels={fuels} />;
  }
  return (
    <SceneErrorBoundary
      fallback={<TankCanvas tank={tank} live={live} fuels={fuels} />}
    >
      <Canvas className="rounded-lg">
        <TankScene config={config} />
      </Canvas>
    </SceneErrorBoundary>
  );
}
