import { describe, expect, it } from 'vitest';
import {
  fillFraction,
  fuelColor,
  interpolateStrapping,
  liquidTopY,
  roundRectPath,
  tankOutlinePath,
  volumeLitersForShape,
} from '../src/lib/tankGeometry';

const vertDims = { diameter: 1.5, height: 2.0 };

describe('volumeLitersForShape (backend fixture vectors)', () => {
  it('vertical_cylinder at 1.0 m == PI * 0.75^2 * 1.0 * 1000', () => {
    const v = volumeLitersForShape(1.0, 'vertical_cylinder', vertDims);
    expect(v).toBeCloseTo(Math.PI * 0.75 ** 2 * 1.0 * 1000, 5);
  });

  it('horizontal_cylinder half-full is (within 0.1%) half of full', () => {
    const full = volumeLitersForShape(1.5, 'horizontal_cylinder', { diameter: 1.5, length: 2.0 });
    const half = volumeLitersForShape(0.75, 'horizontal_cylinder', { diameter: 1.5, length: 2.0 });
    expect(half).toBeCloseTo(full / 2, -3);
  });

  it('rectangular at 0.5 m == 0.5 * width * length * 1000', () => {
    const v = volumeLitersForShape(0.5, 'rectangular', { width: 1.0, length: 2.0, height: 1.5 });
    expect(v).toBeCloseTo(0.5 * 1.0 * 2.0 * 1000, 5);
  });

  it('spherical full == 4/3 PI r^3 * 1000 and half == full/2', () => {
    const full = volumeLitersForShape(2.0, 'spherical', { diameter: 2.0 });
    expect(full).toBeCloseTo((4 / 3) * Math.PI * 1 ** 3 * 1000, 4);
    const half = volumeLitersForShape(1.0, 'spherical', { diameter: 2.0 });
    expect(half).toBeCloseTo(full / 2, -2);
  });

  it('custom_strapping cubic spline interpolates smoothly', () => {
    const pts = [
      { height: 0.0, volume: 0.0 },
      { height: 1.0, volume: 100.0 },
      { height: 2.0, volume: 250.0 },
    ];
    const mid = interpolateStrapping(pts, 1.5, 'cubic_spline');
    expect(mid).toBeGreaterThan(100.0);
    expect(mid).toBeLessThan(300.0);
    expect(Math.abs(mid - 190.0)).toBeLessThan(40.0);
  });

  it('linear strapping interpolates exactly', () => {
    const pts = [
      { height: 0.0, volume: 0.0 },
      { height: 1.0, volume: 100.0 },
      { height: 2.0, volume: 250.0 },
    ];
    expect(interpolateStrapping(pts, 1.5, 'linear')).toBeCloseTo(175.0, 5);
  });

  it('strapping clamps outside the domain', () => {
    const pts = [
      { height: 0.0, volume: 0.0 },
      { height: 1.0, volume: 100.0 },
    ];
    expect(interpolateStrapping(pts, -1.0, 'linear')).toBeCloseTo(0.0, 5);
    expect(interpolateStrapping(pts, 2.0, 'linear')).toBeCloseTo(100.0, 5);
  });
});

describe('SVG helpers', () => {
  it('fillFraction is level/height for vertical-ish', () => {
    expect(fillFraction(1.0, 'vertical_cylinder', vertDims)).toBeCloseTo(0.5, 5);
  });

  it('liquidTopY maps 50% fill to the vertical midpoint', () => {
    const box = { x: 4, y: 4, w: 88, h: 112 };
    expect(liquidTopY(1.0, 'vertical_cylinder', vertDims, box)).toBeCloseTo(4 + 112 * 0.5, 5);
  });

  it('tankOutlinePath returns a closed path', () => {
    const d = tankOutlinePath('vertical_cylinder', { x: 4, y: 4, w: 88, h: 112 });
    expect(d.startsWith('M ')).toBe(true);
    expect(d.endsWith(' Z')).toBe(true);
  });

  it('roundRectPath starts at the top-left corner', () => {
    const d = roundRectPath(4, 4, 88, 112, 12);
    expect(d.startsWith('M 16 4')).toBe(true);
    expect(d.endsWith(' Z')).toBe(true);
  });

  it('fuelColor maps known fuel codes', () => {
    expect(fuelColor('diesel')).toBe('#60a5fa');
    expect(fuelColor('gasoline')).toBe('#f59e0b');
    expect(fuelColor('unknown')).toBe('#0ea5e9');
  });
});
