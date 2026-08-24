/* `window.ZoneEditor` tipi.
 *
 * Muharrir manbasi `chaqimchi_ai/local/static/zone-editor.js` da yotadi
 * va u ATAYLAB bundle qilinmaydi: Windows payload `cloud/` ni
 * ko'chirmaydi, ya'ni bundle qilingan nusxa qurilmadagi bilan bir kun
 * ajralib ketardi.  Uning o'rniga skript ish vaqtida
 * `/vendor/zone-editor.js` dan yuklanadi.
 */

export {};

export type ZoneShape = {
  name: string;
  camera_id: string;
  polygon: [number, number][];
  restricted?: boolean;
  queue?: boolean;
  shelf?: boolean;
  dwell_sec?: number;
};

export type LineShape = {
  name: string;
  camera_id: string;
  start: [number, number];
  end: [number, number];
  swap_direction?: boolean;
};

export type ZoneEditorInstance = {
  load(config: { zones?: unknown[]; lines?: unknown[] }, cameraId: string): void;
  setImage(image: HTMLImageElement | null): void;
  setCamera(cameraId: string): void;
  setMode(mode: "zone" | "line"): void;
  addPreset(type: "queue" | "shelf" | "restricted" | "entrance", customName?: string): boolean;
  serialise(): { zones: ZoneShape[]; lines: LineShape[] };
  visibleZones(): ZoneShape[];
  visibleLines(): LineShape[];
  draw(): void;
  zones: ZoneShape[];
  lines: LineShape[];
};

declare global {
  interface Window {
    ZoneEditor?: new (
      canvas: HTMLCanvasElement,
      options: {
        askName?: (title: string, fallback: string) => string | null;
        confirm?: (message: string) => boolean;
        onChange?: () => void;
      },
    ) => ZoneEditorInstance;
  }
}
