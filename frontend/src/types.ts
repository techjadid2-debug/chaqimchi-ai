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
  /** Bu turdagi hodisaga qurilma kadr ILADIMI.  «Kadr hali yuklanmagan»
   *  va «bu turda kadr umuman olinmaydi» ikki boshqa javob — ularni bir
   *  xil ko'rsatish ega uchun jimgina yolg'on bo'lardi. */
  media_expected?: boolean;
};

/** Vaqt lentasining bitta soati.  `by_type` bo'sh bo'lishi mumkin:
 *  javobda 24 ta katak DOIM keladi (o'q to'liq kun bo'lsin), panel esa
 *  `total === 0` bo'lgan soatga hech narsa chizmaydi. */
export type TimelineHour = {
  hour: number;
  total: number;
  with_media: number;
  by_type: Record<string, number>;
};

export type TimelineAnswer = {
  date: string;
  camera_id?: string | null;
  hours: TimelineHour[];
  /** Faqat O'SHA kuni bor turlar — afsona shu ro'yxatdan quriladi. */
  types: { type: string; label?: string; total: number }[];
  total: number;
};
export type TrendPoint = { date?: string; day?: string; entries?: number; entered?: number; count?: number };

/** Kirgan mijozlarning anonim jins/yosh yig'indisi.
 *
 * Kalit BUTUNLAY yo'q bo'lishi mumkin va bu ikki xil ma'no beradi:
 * tarifda yopiq (server uni hisobotdan olib tashlaydi) yoki bugun
 * hali hech kim kirmagan.  Ikkalasini `hasFeature()` ajratadi —
 * shuning uchun karta avval tarifni tekshiradi. */
export type Demografiya = {
  hisoblangan: number;
  /** Foizlar (eski shakl, orqaga moslik). */
  jins?: { ayol?: number; erkak?: number };
  /** Sonlar — "nechtasi" savoliga to'g'ridan-to'g'ri javob. */
  jins_soni?: { ayol?: number; erkak?: number };
  yosh?: Record<string, number>;
};

export type Dashboard = {
  site: {
    id: string;
    name: string;
    address?: string;
    connection: string;
    minutes_since_seen?: number | null;
    cameras_active?: number;
    cameras_expected?: number;
    plan?: {
      name?: string;
      code?: string;
      /** Tarifda ochiq panel bo'limlari — qulf shu ro'yxatdan yasaladi. */
      panel_features?: string[];
    };
  };
  /* `today` ataylab to'liq tiplashtirilmagan: `OwnerHome.num()` va
     `owner.tsx` dagi `value()` uni `Record<string, unknown>` sifatida
     aylanib chiqadi.  Kesishma bilan faqat kerakli tarmoq
     torlashtiriladi — qolgani o'sha-o'shaligicha qoladi. */
  today: Record<string, unknown> & { demografiya?: Demografiya };
  /** Do'kon kompyuterining holati.  Hali heartbeat kelmagan bo'lsa
   *  `null`; o'lchanmagan ko'rsatkich esa kalit sifatida ham kelmaydi. */
  device?: {
    received_at?: string;
    cpu_percent?: number;
    ram_percent?: number;
    disk_percent?: number;
    temperature_c?: number;
    free_disk_gb?: number;
    uptime_sec?: number;
    app_version?: string;
    hot?: boolean;
  } | null;
  cameras: Camera[];
  camera_states: CameraState[];
  events: EventItem[];
  trend: TrendPoint[];
  subscription?: { status?: string; days_left?: number; monthly_price_uzs?: number; subscription_until?: string };
  capabilities?: {
    cameras?: { ready?: boolean; active?: number; expected?: number; reason?: string };
    edge_config?: { ready?: boolean; revision?: number; reason?: string };
    features?: { panel?: string[]; edge?: string[] };
    /** Chiziq/zona chizilganmi — "nega 0?" savolining eng keng javobi. */
    geometry?: { ready?: boolean; lines_drawn?: boolean; zones_drawn?: boolean; reason?: string };
  };
  diagnostics?: { created_at?: string; payload?: { outbox?: { pending?: number; poisoned?: number }; cloud?: { dns_ok?: boolean } } } | null;
  /** Chegara tufayli saqlanmagan rasm soni — 0 dan katta bo'lsa egaga aytiladi. */
  media_dropped?: number;
  /** Rasm/klip qancha soat yashaydi.  Panel buni O'ZIDA saqlamasin:
   *  ikki fayldagi ikki son bir-birini inkor qilishi mumkin va buni
   *  hech qaysi test ko'rmasdi. */
  media_retention_hours?: number;
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
