// Service worker: makes the panel installable and caches only static files
// (fonts, icons, CSS). Pages with appointments are never stored on the phone.
const CACHE = "nobat-static-v7";
const ASSETS = ["/static/themes.css?v=1", "/static/style.css?v=8", "/static/theme.js?v=2",
                "/static/app.js?v=3", "/static/fonts/Vazirmatn.woff2",
                "/static/icons/icon-192.png", "/static/icons/icon-512.png",
                "/static/icons/icon-maskable-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request)));
    return;
  }
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() =>
      new Response(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">' +
        '<body dir="rtl" style="font-family:Tahoma;text-align:center;padding:40px">' +
        "<h2>اتصال برقرار نیست</h2><p>اینترنت گوشی را بررسی کنید و دوباره امتحان کنید.</p></body>",
        { headers: { "Content-Type": "text/html; charset=utf-8" } })));
  }
});
