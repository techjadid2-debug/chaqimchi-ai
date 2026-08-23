/* Panel bo'ylab bo'lishiladigan tiplar.
 *
 * Ilgari ular `owner.tsx` boshida turardi va bosh sahifani alohida
 * faylga ajratganda aylanma import (`owner.tsx` ↔ `OwnerHome.tsx`)
 * paydo bo'lardi. */

export type Site = {
  id: string;
  name: string;
  address?: string;
  connection?: string;
  cameras_active?: number;
  cameras_expected?: number;
  role?: string;
};

export type CameraState = { camera_id: string; state: string; reason?: string; reported_at?: string };
export type Camera = { camera_id: string; label?: string; enabled?: boolean };
export type EventItem = {
  id?: string;
  event_type: string;
  label?: string;
  camera_id?: string;
  created_at?: string;
  occurred_at?: string;
};
export type TrendPoint = { date?: string; day?: string; entries?: number; entered?: number; count?: number };

export type Dashboard = {
  site: {
    id: string;
    name: string;
    address?: string;
    connection: string;
    minutes_since_seen?: number | null;
    cameras_active?: number;
    cameras_expected?: number;
    plan?: { name?: string };
  };
  today: Record<string, unknown>;
  cameras: Camera[];
  camera_states: CameraState[];
  events: EventItem[];
  trend: TrendPoint[];
  subscription?: { status?: string; days_left?: number; monthly_price_uzs?: number; subscription_until?: string };
  updated_at: string;
  revision?: string;
};

export type Employee = {
  id: string;
  name?: string;
  external_id?: string;
  active?: boolean;
  enrollment_status?: string;
  photos?: { id: string }[];
};
export type Invoice = {
  id: string;
  months: number;
  amount_uzs: number;
  state: string;
  created_at?: string;
  paid_at?: string;
  pay_url?: string;
  payme_url?: string;
  click_url?: string;
};
export type TelegramMember = {
  id: string;
  telegram_id: string;
  role: string;
  display_name?: string;
  digest_muted?: boolean;
  created_at?: string;
};
