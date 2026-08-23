/* Kesh nomi — RELIZ QOIDASI.
 *
 * Panel fayllari o'zgarganda bu raqamni oshiring: `activate` da nomi
 * boshqa bo'lgan barcha keshlar o'chiriladi, ya'ni qurilmalarda eski
 * nusxa qolib ketmaydi.  Bundle nomlarida mazmun xeshi bo'lgani uchun
 * odatda bu shart emas, lekin manifest yoki ikonka kabi xeshsiz
 * fayllar o'zgarganda aynan shu yagona yo'l.
 *
 *   -static-1 → 2026-08-24: yangi dizayn, PWA ikonkalari
 */
const CACHE = "chaqimchi-ui-v2-static-2";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith("/assets/v2/")) return;
  event.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match(event.request);
    const network = fetch(event.request).then((response) => { if (response.ok) cache.put(event.request, response.clone()); return response; });
    return cached || network;
  }));
});
