import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import type { FuelType, TankRead, TankUpdatePayload } from '../../lib/apiTypes';
import { canManage } from '../../lib/roles';
import { useAuthStore } from '../../store/auth';
import { Modal } from '../ui/Modal';
import { ConfirmDialog } from '../ui/confirm';
import { Field, Input } from '../ui/fields';

/**
 * Edit tank.
 *
 * Grouped as operators think about it — identity, physical geometry, sensor
 * calibration, and the thresholds that raise alarms — rather than as a flat dump
 * of the schema, because the threshold block is the one that changes what the
 * platform *does* and deserves the most prominence.
 *
 * Site is intentionally not editable: moving a tank between sites would change
 * which tenant owns its history.
 */

/** Threshold fields, grouped by what they trigger. */
const THRESHOLD_FIELDS: Array<{
  key: keyof TankUpdatePayload;
  label: string;
  hint: string;
}> = [
  { key: 'critical_level_threshold', label: 'Critical level (m)', hint: 'Emergency low' },
  { key: 'low_level_threshold', label: 'Low level (m)', hint: 'Warning low' },
  { key: 'high_level_threshold', label: 'High level (m)', hint: 'Warning high' },
  { key: 'low_volume_threshold', label: 'Low volume (L)', hint: 'Warning low' },
  { key: 'high_volume_threshold', label: 'High volume (L)', hint: 'Warning high' },
];

const GEOMETRY_FIELDS: Array<{ key: keyof TankUpdatePayload; label: string; step?: string }> = [
  { key: 'tank_volume', label: 'Capacity (L)', step: 'any' },
  { key: 'tank_height', label: 'Height (m)', step: 'any' },
  { key: 'tank_length', label: 'Length (m)', step: 'any' },
  { key: 'tank_width', label: 'Width (m)', step: 'any' },
  { key: 'dish_depth', label: 'Dish depth (m)', step: 'any' },
];

const CALIBRATION_FIELDS: Array<{ key: keyof TankUpdatePayload; label: string; step?: string }> = [
  { key: 'elevation', label: 'Elevation (m)', step: 'any' },
  { key: 'calibration_factor', label: 'Calibration factor', step: 'any' },
  { key: 'atmospheric_pressure', label: 'Atmospheric pressure (bar)', step: 'any' },
];

/** Trim a nullable number field: blank means "leave unchanged". */
function num(value: string): number | undefined {
  if (value.trim() === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function EditTankDialog({
  tank,
  fuels,
  onClose,
}: {
  tank: TankRead;
  fuels: FuelType[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: tank.name,
    fuel_type_id: tank.fuel_type_id ?? '',
    tank_volume: String(tank.tank_volume ?? ''),
    tank_height: tank.tank_height === null ? '' : String(tank.tank_height),
    tank_length: tank.tank_length === null ? '' : String(tank.tank_length),
    tank_width: tank.tank_width === null ? '' : String(tank.tank_width),
    dish_depth: tank.dish_depth === null ? '' : String(tank.dish_depth),
    elevation: tank.elevation === null ? '' : String(tank.elevation),
    calibration_factor: String(tank.calibration_factor ?? ''),
    atmospheric_pressure: String(tank.atmospheric_pressure ?? ''),
    critical_level_threshold: tank.critical_level_threshold === null ? '' : String(tank.critical_level_threshold),
    low_level_threshold: tank.low_level_threshold === null ? '' : String(tank.low_level_threshold),
    high_level_threshold: tank.high_level_threshold === null ? '' : String(tank.high_level_threshold),
    low_volume_threshold: tank.low_volume_threshold === null ? '' : String(tank.low_volume_threshold),
    high_volume_threshold: tank.high_volume_threshold === null ? '' : String(tank.high_volume_threshold),
    is_active: tank.is_active,
  });

  const set =
    (k: keyof typeof form) =>
    (e: { target: { value: string } }) =>
      setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = useMutation({
    mutationFn: () => {
      const payload: TankUpdatePayload = {
        name: form.name.trim(),
        fuel_type_id: form.fuel_type_id || undefined,
        is_active: form.is_active,
      };
      for (const { key } of GEOMETRY_FIELDS) {
        const v = num(form[key as keyof typeof form] as string);
        if (v !== undefined) (payload as Record<string, unknown>)[key] = v;
      }
      for (const { key } of CALIBRATION_FIELDS) {
        const v = num(form[key as keyof typeof form] as string);
        if (v !== undefined) (payload as Record<string, unknown>)[key] = v;
      }
      for (const { key } of THRESHOLD_FIELDS) {
        const v = num(form[key as keyof typeof form] as string);
        if (v !== undefined) (payload as Record<string, unknown>)[key] = v;
      }
      return api.updateTank(tank.id, payload);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tanks'] });
      void qc.invalidateQueries({ queryKey: ['tank', tank.id] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Could not save the tank.'),
  });

  // Validate the *edited* values, not the stored ones: checking the tank prop
  // would never react to the operator changing a threshold.
  const critical = num(form.critical_level_threshold);
  const low = num(form.low_level_threshold);
  const high = num(form.high_level_threshold);
  const invalidRange =
    critical !== undefined && low !== undefined ? critical > low : false;
  const invalidHigh = high !== undefined && low !== undefined ? high <= low : false;

  return (
    <Modal title={`Edit ${tank.name}`} onClose={onClose} wide>
      <div className="space-y-4">
        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-primary">Identity</h4>
          <Field label="Name" htmlFor="edit-tank-name">
            <Input id="edit-tank-name" value={form.name} onChange={set('name')} />
          </Field>
          <Field label="Fuel type" htmlFor="edit-tank-fuel">
            <select
              id="edit-tank-fuel"
              className="w-full border border-line-strong rounded px-3 py-2 text-sm"
              value={form.fuel_type_id}
              onChange={set('fuel_type_id')}
            >
              {fuels.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </Field>
          <p className="text-xs text-muted">
            Sensor serial {tank.sensor_serial_number} · site is fixed: moving a tank would
            reassign the ownership of its history.
          </p>
          <label className="flex items-center gap-2 text-sm text-secondary">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Active (an inactive tank is excluded from operational views)
          </label>
        </section>

        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-primary">Physical geometry</h4>
          <div className="grid grid-cols-2 gap-3">
            {GEOMETRY_FIELDS.map(({ key, label, step }) => (
              <Field key={key} label={label} htmlFor={`edit-tank-${key}`}>
                <input
                  id={`edit-tank-${key}`}
                  type="number"
                  step={step}
                  className="w-full border border-line-strong rounded px-3 py-2 text-sm"
                  value={form[key as keyof typeof form] as string}
                  onChange={set(key as keyof typeof form)}
                />
              </Field>
            ))}
          </div>
        </section>

        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-primary">Sensor calibration</h4>
          <div className="grid grid-cols-3 gap-3">
            {CALIBRATION_FIELDS.map(({ key, label, step }) => (
              <Field key={key} label={label} htmlFor={`edit-tank-${key}`}>
                <input
                  id={`edit-tank-${key}`}
                  type="number"
                  step={step}
                  className="w-full border border-line-strong rounded px-3 py-2 text-sm"
                  value={form[key as keyof typeof form] as string}
                  onChange={set(key as keyof typeof form)}
                />
              </Field>
            ))}
          </div>
          <p className="text-xs text-muted">
            Atmospheric pressure is subtracted from the probe reading before the level is
            derived. If it is left at 0 while the probe reports absolute pressure, every level
            is wrong.
          </p>
        </section>

        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-primary">Alarm thresholds</h4>
          <div className="grid grid-cols-2 gap-3">
            {THRESHOLD_FIELDS.map(({ key, label, hint }) => (
              <Field key={key} label={label} htmlFor={`edit-tank-${key}`}>
                <input
                  id={`edit-tank-${key}`}
                  type="number"
                  step="any"
                  placeholder="disabled"
                  className="w-full border border-line-strong rounded px-3 py-2 text-sm"
                  value={form[key as keyof typeof form] as string}
                  onChange={set(key as keyof typeof form)}
                />
                <span className="mt-0.5 block text-xs text-muted">{hint}</span>
              </Field>
            ))}
          </div>
          {invalidRange ? (
            <p role="alert" className="text-sm text-danger-fg">
              The critical level ({critical} m) is above the low level ({low} m): a full tank
              would satisfy the critical alarm.
            </p>
          ) : null}
          {invalidHigh ? (
            <p role="alert" className="text-sm text-danger-fg">
              The high level ({high} m) must sit above the low level ({low} m), otherwise the
              tank alarms constantly.
            </p>
          ) : null}
          <p className="text-xs text-muted">
            Leave a threshold blank to keep it as it is. An alarm clears once the measurement
            returns inside the band, with hysteresis so it does not flap.
          </p>
        </section>
      </div>

      {error ? <p className="mt-2 text-sm text-danger-fg">{error}</p> : null}
      <div className="flex justify-end gap-2 pt-4">
        <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-secondary">
          Cancel
        </button>
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending || form.name.trim() === '' || invalidRange || invalidHigh}
          className="rounded bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Modal>
  );
}

/**
 * Deactivate (soft delete).
 *
 * Deliberately not labelled "Delete": the server soft-deletes, the tank keeps
 * its telemetry and alarm history, and it can be restored. Saying "delete" here
 * would imply otherwise.
 */
export function DeactivateTankDialog({
  tank,
  onClose,
}: {
  tank: TankRead;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const deactivate = useMutation({
    mutationFn: () => api.deleteTank(tank.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tanks'] });
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.detail : 'Could not deactivate the tank.'),
  });

  if (error) {
    return (
      <Modal title="Deactivate failed" onClose={onClose}>
        <p className="text-sm text-danger-fg">{error}</p>
      </Modal>
    );
  }

  return (
    <ConfirmDialog
      title="Deactivate tank"
      message={`Deactivate "${tank.name}"? It stops appearing in operational views and stops raising alarms. Its telemetry and alarm history are kept, and an administrator can restore it.`}
      confirmLabel="Deactivate"
      onCancel={onClose}
      onConfirm={() => deactivate.mutate()}
    />
  );
}

/** Restore a soft-deleted tank. */
export function RestoreTankDialog({
  tank,
  onClose,
}: {
  tank: TankRead;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const restore = useMutation({
    mutationFn: () => api.restoreTank(tank.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['tanks'] });
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.detail : 'Could not restore the tank.'),
  });

  if (error) {
    return (
      <Modal title="Restore failed" onClose={onClose}>
        <p className="text-sm text-danger-fg">{error}</p>
      </Modal>
    );
  }

  return (
    <ConfirmDialog
      title="Restore tank"
      message={`Restore "${tank.name}"? It will appear in operational views again.`}
      confirmLabel="Restore"
      onCancel={onClose}
      onConfirm={() => restore.mutate()}
    />
  );
}

/** Actions for one tank row, shown only to a management role. */
export function TankRowActions({ tank }: { tank: TankRead }) {
  const user = useAuthStore((s) => s.user);
  const [editing, setEditing] = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const [restoring, setRestoring] = useState(false);

  // The server enforces this too; hiding it keeps the UI honest about what the
  // operator can actually do.
  if (!canManage(user?.role)) return null;

  return (
    <div className="flex justify-end gap-3 px-4 py-2">
      <button
        type="button"
        className="text-brand-dark hover:underline"
        onClick={() => setEditing(true)}
      >
        Edit
      </button>
      {tank.is_active ? (
        <button
          type="button"
          className="text-rose-600 hover:underline"
          onClick={() => setDeactivating(true)}
        >
          Deactivate
        </button>
      ) : (
        <button
          type="button"
          className="text-brand-dark hover:underline"
          onClick={() => setRestoring(true)}
        >
          Restore
        </button>
      )}
      {editing ? (
        <TankEditHost tank={tank} onClose={() => setEditing(false)} />
      ) : null}
      {deactivating ? (
        <DeactivateTankDialog tank={tank} onClose={() => setDeactivating(false)} />
      ) : null}
      {restoring ? <RestoreTankDialog tank={tank} onClose={() => setRestoring(false)} /> : null}
    </div>
  );
}

/** Loads the fuel catalogue for the edit dialog. */
function TankEditHost({ tank, onClose }: { tank: TankRead; onClose: () => void }) {
  const { data: fuels = [] } = useQuery({
    queryKey: ['fuel-types'],
    queryFn: () => api.listFuelTypes(),
  });
  return <EditTankDialog tank={tank} fuels={fuels} onClose={onClose} />;
}