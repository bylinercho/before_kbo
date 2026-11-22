// tools/17_make_app.py 가 만든 파일. 앱형 화면(app.html)을 오프라인에서도 열 수 있게 자료를 저장해 둔다.
// 방식: 인터넷이 되면 항상 최신을 받고(받은 것을 저장), 안 되면 저장해 둔 것을 쓴다. index.html 은 건드리지 않는다.
const V = "bk-app-v1";
const CORE = ["app.html", "theme-paper.css", "data.js", "awards.js", "videos.js", "rumors.js", "reports.js", "careers.js", "manifest.json",
  "img/logo.png", "img/gg.png", "img/mvp.png", "img/taegeuk.png", "img/icons/icon-192.png"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(V).then(c => Promise.allSettled(CORE.map(u => c.add(new Request(u, {cache: "reload"}))))));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET") return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;                                   // 외부(구글 폰트 등)는 건드리지 않는다
  if (r.mode === "navigate" && !u.pathname.endsWith("/app.html")) return;    // 다른 페이지 이동은 그대로 둔다
  e.respondWith(
    fetch(r).then(res => { if (res.ok) { const cp = res.clone(); caches.open(V).then(c => c.put(r, cp)); } return res; })
      .catch(() => caches.match(r).then(m => m || (r.mode === "navigate" ? caches.match("app.html") : Response.error())))
  );
});
