export interface UserRead {
  id: string;
  username: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: string;
  is_superuser: boolean;
  is_active: boolean;
  phone: string | null;
  last_login: string | null;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserRead;
}

export type FuelCode = 'gasoline' | 'diesel' | 'kerosene' | 'jet_fuel' | 'ethanol' | string;

export interface FuelType {
  id: string;
  code: FuelCode;
  name: string;
  base_density: number;
  thermal_expansion_coeff: number;
  max_vapor_pressure: number;
  viscosity_cst: number;
  created_at: string;
}

export type TankShape =
  | 'vertical_cylinder'
  | 'horizontal_cylinder'
  | 'rectangular'
  | 'spherical'
  | 'horizontal_elliptical_ends'
  | 'custom_strapping';

export interface TankRead {
  id: string;
  name: string;
  site_id: string;
  sensor_serial_number: string;
  device_address: number;
  tank_orientation: 'vertical' | 'horizontal';
  tank_diameter: number;
  tank_height: number | null;
  tank_length: number | null;
  tank_volume: number;
  tank_shape: TankShape | null;
  fuel_type_id: string;
  dish_depth: number | null;
  tank_width: number | null;
  strapping_table_id: string | null;
  elevation: number | null;
  calibration_factor: number;
  atmospheric_pressure: number;
  low_level_threshold: number | null;
  critical_level_threshold: number | null;
  high_level_threshold: number | null;
  low_volume_threshold: number | null;
  high_volume_threshold: number | null;
  is_active: boolean;
  gateway_mac: string | null;
  created_at: string;
  connection_status: string;
  last_connection: string | null;
}

export interface TankCreatePayload {
  name: string;
  site_id: string;
  sensor_serial_number: string;
  device_address?: number;
  tank_orientation: 'vertical' | 'horizontal';
  tank_shape: TankShape;
  tank_diameter?: number;
  tank_height?: number;
  tank_length?: number;
  tank_width?: number;
  dish_depth?: number;
  tank_volume: number;
  fuel_type_id: string;
  low_level_threshold?: number | null;
  critical_level_threshold?: number | null;
  high_level_threshold?: number | null;
  low_volume_threshold?: number | null;
  high_volume_threshold?: number | null;
}

export interface TelemetryPoint {
  timestamp: string;
  pressure: number | null;
  temperature: number | null;
  level: number | null;
  volume: number | null;
  flow_rate: number | null;
  fill_percent: number | null;
  is_outlier: boolean;
  gov_volume?: number | null;
  net_volume?: number | null;
  density_at_temperature?: number | null;
}

export interface AlarmSummary {
  id: string;
  tank_id: string;
  timestamp: string;
  type: string;
  level: string;
  message: string;
  value: number | null;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

export interface StrappingPoint {
  height: number;
  volume: number;
}

export interface StrappingTable {
  id: string;
  tank_id: string;
  calibration_data: StrappingPoint[];
  interpolation_method: 'linear' | 'cubic_spline';
  created_at: string;
}

export interface AllocationRead {
  id: string;
  employee_id: string;
  employee_name: string;
  invoice_number: string | null;
  allocated_liters: number;
  dispensed_liters: number;
  remaining_liters: number;
  status: string;
  created_at: string;
}

export interface TransactionRead {
  id: number;
  station_id: string;
  dispenser_id: string;
  employee_id: string;
  requested_liters: number;
  actual_liters: number;
  secret_totalizer_before: number;
  secret_totalizer_after: number;
  status: string;
  created_at: string;
}

export interface TotalizerPoint {
  timestamp: string;
  station_id: string;
  dispenser_id: string;
  totalizer_value: number;
  cumulative_liters: number;
  source: string;
}

export interface Dispenser {
  id: string;
  name: string;
  station_id: string;
  serial_number: string;
  modbus_address: number;
  dispenser_model: string | null;
  is_active: boolean;
}

export interface Station {
  id: string;
  name: string;
  site_id: string;
  serial_number: string;
  raspberry_pi_id: string | null;
  firmware_version: string | null;
  connection_status: string;
  last_heartbeat: string | null;
}

export interface Company {
  id: string;
  name: string;
  address: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  created_at: string;
}

export interface Site {
  id: string;
  name: string;
  company_id: string;
  address: string | null;
  location: string | null;
  is_active: boolean;
  created_at: string;
}

export type ListTanksResponse = TankRead[];

// --- Org management ---
export interface CompanyCreate {
  name: string;
  address?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
}

export interface CompanyUpdate {
  name?: string;
  address?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
}

export interface SiteCreate {
  company_id: string;
  name: string;
  address?: string | null;
  location?: string | null;
  is_active?: boolean;
}

export interface SiteUpdate {
  name?: string;
  address?: string | null;
  location?: string | null;
  is_active?: boolean;
}

export interface StationCreate {
  site_id: string;
  name: string;
  serial_number: string;
  raspberry_pi_id?: string | null;
  firmware_version?: string | null;
}

export interface StationUpdate {
  name?: string;
  raspberry_pi_id?: string | null;
  firmware_version?: string | null;
  connection_status?: string;
}

export interface DispenserCreate {
  station_id?: string;
  name: string;
  serial_number: string;
  modbus_address: number;
  dispenser_model?: string;
}

export interface DispenserUpdate {
  is_active?: boolean;
  name?: string;
  dispenser_model?: string;
  modbus_address?: number;
}

// --- Quota/Allocation ---
export interface Allocation {
  id: string;
  employee_id: string;
  employee_name: string;
  invoice_number: string | null;
  allocated_liters: number;
  dispensed_liters: number;
  remaining_liters: number;
  status: string;
  created_at: string;
}

export interface QuotaAllocation {
  employee_id: string;
  employee_name?: string;
  phone?: string;
  invoice_number?: string;
  allocated_liters: number;
}

export interface ExcelIngestOutcome {
  result: {
    total_rows: number;
    successful_rows: number;
    failed_rows: number;
    errors: { row: number; error: string }[];
  };
}

// --- Code operations ---
export interface CodeValidateResponse {
  valid: boolean;
  employee_name?: string;
  remaining_liters?: number;
  code_id?: string;
  reason?: string;
}

export interface DispenseRequest {
  code: string;
  station_id: string;
  dispenser_id: string;
  requested_liters: number;
  actual_liters: number;
  secret_totalizer_before: number;
  secret_totalizer_after: number;
}

export interface DispenseCompleteResponse {
  id: string;
  status: string;
  requested_liters: number;
  actual_liters: number;
}

// --- Notifications ---
export interface NotificationGatewayRead {
  id: string;
  name: string;
  type: string;
  config_json: Record<string, unknown>;
  is_active: boolean;
  priority: number;
  created_at: string;
}

// --- Fuel types ---
export interface FuelTypeCreate {
  code: string;
  name: string;
  base_density: number;
  thermal_expansion_coeff: number;
  max_vapor_pressure: number;
  viscosity_cst: number;
}

export type TankTransaction = Pick<TransactionRead, 'id' | 'actual_liters' | 'status' | 'created_at'> & { tank_id: string };