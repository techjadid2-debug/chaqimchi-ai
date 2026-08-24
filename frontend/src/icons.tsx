import type { ReactNode } from "react";

const paths: Record<string, ReactNode> = {
  home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10M9 20v-6h6v6"/></>,
  camera: <><rect x="3" y="6" width="18" height="13" rx="3"/><path d="m8 6 1.5-2h5L16 6"/><circle cx="12" cy="12.5" r="3.5"/></>,
  chart: <><path d="M4 19V9M10 19V5M16 19v-8M22 19H2"/></>,
  users: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2c0-3 2.5-5 6-5s6 2 6 5v2M16 5.5a3 3 0 0 1 0 5.8M17 14c2.5.3 4 1.8 4 4v2"/></>,
  heat: <><path d="M12 3c3 4 5 6.5 5 10a5 5 0 0 1-10 0c0-2.4 1.4-4.7 3.1-6.9.3 2 .9 3.2 1.9 4.1.8-2.6.8-4.9 0-7.2Z"/></>,
  branch: <><path d="M4 21V8l8-5 8 5v13M8 21v-7h8v7M2 21h20"/></>,
  report: <><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></>,
  card: <><rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20M6 15h4"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
  logout: <><path d="M10 4H4v16h6M14 8l4 4-4 4M8 12h10"/></>,
  pulse: <><path d="M3 12h4l2-5 4 10 2-5h6"/></>,
  store: <><path d="M4 10v10h16V10M3 4h18l-1 6H4L3 4Z"/><path d="M9 20v-6h6v6"/></>,
  server: <><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h7M11 17h7"/></>,
  shield: <><path d="M12 3 4 6v5c0 5 3.4 8.4 8 10 4.6-1.6 8-5 8-10V6l-8-3Z"/><path d="m9 12 2 2 4-5"/></>,
  invoice: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3Z"/><path d="M9 8h6M9 12h6"/></>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  close: <><path d="m5 5 14 14M19 5 5 19"/></>,
  eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5.5l3.5 2"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/></>,
  telegram: <><path d="M21 4 3 11l5 2 2 6 3-4 5 4 3-15Z"/><path d="m8 13 9-6-6 8"/></>,
  download: <><path d="M12 3v11m-4-4 4 4 4-4M5 20h14"/></>,
  cpu: <><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/></>,
  shapes: <><path d="M3 17 9 5l6 12z"/><circle cx="18" cy="17" r="3.4"/></>,
};

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.more}</svg>;
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return <div className="brand" aria-label="Chaqimchi AI">
    <img className="brand-mark" src="/assets/chaqimchi-logo-new.png" alt="" />
    {compact ? null : <span>Chaqimchi <b>AI</b></span>}
  </div>;
}
