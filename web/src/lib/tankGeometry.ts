export type TankShape =
  | 'vertical_cylinder'
  | 'horizontal_cylinder'
  | 'rectangular'
  | 'spherical'
  | 'horizontal_elliptical_ends'
  | 'custom_strapping';

export interface ShapeDims {
  diameter?: number | null;
  length?: number | null;
  height?: number | null;
  width?: number | null;
  dishDepth?: number | null;
}

export interface StrappingPoint {
  height: number;
  volume: number;
}

export interface StrappingRef {
  points: StrappingPoint[];
  method: 'linear' | 'cubic_spline';
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/** Liters in a horizontal cylinder up to `level` (m); diameter m, length m. */
export function horizontalCylinderLiters(level: number, diameter: number, length: number): number {
  const lvl = clamp(level, 0, diameter);
  const r = diameter / 2;
  if (lvl <= 0.001) return 0;
  if (lvl >= diameter - 0.001) return Math.PI * r * r * length * 1000;
  let area: number;
  if (lvl <= r) {
    const theta = 2 * Math.acos((r - lvl) / r);
    area = (r * r * (theta - Math.sin(theta))) / 2;
  } else {
    const hEmpty = diameter - lvl;
    const theta = 2 * Math.acos((r - hEmpty) / r);
    area = Math.PI * r * r - (r * r * (theta - Math.sin(theta))) / 2;
  }
  return area * length * 1000;
}

function verticalCylinderLiters(level: number, diameter: number, height: number): number {
  return Math.PI * (diameter / 2) ** 2 * clamp(level, 0, height) * 1000;
}

function rectangularLiters(level: number, width: number, length: number, height: number): number {
  return length * width * clamp(level, 0, height) * 1000;
}

function sphericalLiters(level: number, diameter: number): number {
  const r = diameter / 2;
  const h = clamp(level, 0, diameter);
  return ((Math.PI * h * h) / 3) * (3 * r - h) * 1000;
}

/** Natural cubic spline: returns an evaluation function over [xs[0], xs[n]]. */
export function naturalCubicSpline(xs: number[], ys: number[]): (x: number) => number {
  const n = xs.length - 1;
  if (n < 1) throw new Error('spline requires at least 2 points');
  const h: number[] = [];
  for (let i = 0; i < n; i++) h[i] = xs[i + 1] - xs[i];
  if (h.some((v) => v <= 0)) throw new Error('spline x values must be strictly ascending');

  const a: number[][] = Array.from({ length: n + 1 }, () => new Array(n + 1).fill(0));
  const rhs: number[] = new Array(n + 1).fill(0);
  for (let i = 1; i < n; i++) {
    a[i][i - 1] = h[i - 1];
    a[i][i] = 2 * (h[i - 1] + h[i]);
    a[i][i + 1] = h[i];
    rhs[i] = 6 * ((ys[i + 1] - ys[i]) / h[i] - (ys[i] - ys[i - 1]) / h[i - 1]);
  }
  a[0][0] = 1;
  a[n][n] = 1;

  for (let i = 1; i <= n; i++) {
    const factor = a[i][i - 1] / a[i - 1][i - 1];
    a[i][i - 1] = 0;
    a[i][i] -= factor * a[i - 1][i];
    rhs[i] -= factor * rhs[i - 1];
  }
  const m2 = new Array(n + 1).fill(0);
  m2[n] = rhs[n] / a[n][n];
  for (let i = n - 1; i >= 0; i--) {
    let s = rhs[i];
    for (let j = i + 1; j <= n; j++) s -= a[i][j] * m2[j];
    m2[i] = s / a[i][i];
  }

  return (x: number): number => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n]) return ys[n];
    let i = 0;
    while (i < n - 1 && xs[i + 1] < x) i++;
    const av = (xs[i + 1] - x) / h[i];
    const bv = (x - xs[i]) / h[i];
    return (
      av * ys[i] +
      bv * ys[i + 1] +
      ((av ** 3 - av) * m2[i] + (bv ** 3 - bv) * m2[i + 1]) * (h[i] * h[i]) / 6
    );
  };
}

export function interpolateStrapping(
  points: StrappingPoint[],
  level: number,
  method: 'linear' | 'cubic_spline'
): number {
  const pts = [...points].sort((a, b) => a.height - b.height).map((p) => [p.height, p.volume] as const);
  if (pts.length < 2) throw new Error('strapping table requires at least 2 points');
  const hs = pts.map((p) => p[0]);
  const vs = pts.map((p) => p[1]);
  if (level <= hs[0]) return vs[0];
  if (level >= hs[hs.length - 1]) return vs[vs.length - 1];
  if (method === 'linear') {
    for (let i = 0; i < hs.length - 1; i++) {
      if (hs[i] <= level && level <= hs[i + 1]) {
        const t = (level - hs[i]) / (hs[i + 1] - hs[i]);
        return vs[i] + t * (vs[i + 1] - vs[i]);
      }
    }
    return vs[0];
  }
  return naturalCubicSpline(hs, vs)(level);
}

/** Liters at a level for a physical shape (mirror of the backend dispatcher). */
export function volumeLitersForShape(
  level: number,
  shape: TankShape,
  dims: ShapeDims,
  strapping?: StrappingRef
): number {
  const d = dims.diameter ?? 0;
  switch (shape) {
    case 'vertical_cylinder':
      return verticalCylinderLiters(level, d, dims.height ?? d);
    case 'rectangular':
      return rectangularLiters(level, dims.width ?? 0, dims.length ?? 0, dims.height ?? 0);
    case 'spherical':
      return sphericalLiters(level, d);
    case 'horizontal_cylinder':
    case 'horizontal_elliptical_ends':
      return horizontalCylinderLiters(level, d, dims.length ?? 0);
    case 'custom_strapping':
      if (!strapping) throw new Error('custom_strapping requires a strapping table');
      return interpolateStrapping(strapping.points, level, strapping.method);
  }
}

export function fillFraction(level: number, shape: TankShape, dims: ShapeDims): number {
  const h =
    shape === 'vertical_cylinder' || shape === 'rectangular' ? dims.height : dims.diameter;
  if (!h || h <= 0) return clamp(level, 0, 1);
  return clamp(level / h, 0, 1);
}

/** Y pixel of the liquid surface inside a drawing box (bottom = full, top = empty). */
export function liquidTopY(level: number, shape: TankShape, dims: ShapeDims, box: Box): number {
  return box.y + box.h * (1 - fillFraction(level, shape, dims));
}

/** Bottom-aligned liquid polygon; clipped to the tank outline by the SVG. */
export function liquidPath(level: number, shape: TankShape, dims: ShapeDims, box: Box): string {
  const y = liquidTopY(level, shape, dims, box);
  return (
    `M ${box.x} ${y} L ${box.x + box.w} ${y} ` +
    `L ${box.x + box.w} ${box.y + box.h} L ${box.x} ${box.y + box.h} Z`
  );
}

export function roundRectPath(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, w / 2, h / 2);
  return (
    `M ${x + rr} ${y} L ${x + w - rr} ${y} ` +
    `A ${rr} ${rr} 0 0 1 ${x + w} ${y + rr} ` +
    `L ${x + w} ${y + h - rr} A ${rr} ${rr} 0 0 1 ${x + w - rr} ${y + h} ` +
    `L ${x + rr} ${y + h} A ${rr} ${rr} 0 0 1 ${x} ${y + h - rr} ` +
    `L ${x} ${y + rr} A ${rr} ${rr} 0 0 1 ${x + rr} ${y} Z`
  );
}

function circlePath(x: number, y: number, w: number, h: number): string {
  const r = Math.max(1, Math.min(w, h) / 2 - 6);
  const cx = x + w / 2;
  const cy = y + h / 2;
  return `M ${cx - r} ${cy} A ${r} ${r} 0 1 0 ${cx + r} ${cy} A ${r} ${r} 0 1 0 ${cx - r} ${cy} Z`;
}

/** Outline path per tank shape within a drawing box (liquid is clipped to it). */
export function tankOutlinePath(shape: TankShape, box: Box): string {
  switch (shape) {
    case 'vertical_cylinder':
      return roundRectPath(box.x, box.y, box.w, box.h, box.w / 2);
    case 'horizontal_cylinder':
    case 'horizontal_elliptical_ends':
      return roundRectPath(box.x, box.y, box.w, box.h, box.h / 2);
    case 'rectangular':
      return roundRectPath(box.x, box.y, box.w, box.h, 6);
    case 'spherical':
      return circlePath(box.x, box.y, box.w, box.h);
    case 'custom_strapping':
      return roundRectPath(box.x, box.y, box.w, box.h, box.w / 2);
  }
}

/** Liquid fill color keyed by fuel type code. */
export function fuelColor(code: string): string {
  switch (code) {
    case 'gasoline':
      return '#f59e0b';
    case 'diesel':
      return '#60a5fa';
    case 'kerosene':
      return '#84cc16';
    case 'jet_fuel':
      return '#f97316';
    case 'ethanol':
      return '#14b8a6';
    default:
      return '#0ea5e9';
  }
}