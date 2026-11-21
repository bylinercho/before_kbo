"""17단계: docs/index.html 로 앱형 화면 docs/app.html 과 PWA 파일(manifest.json, sw.js)을 만든다.

실행:  python -I tools/17_make_app.py
- index.html 은 건드리지 않는다. index.html 을 고친 뒤 이 스크립트를 다시 돌리면 app.html 도 따라간다.
- 앱형 바뀐 점: 아래쪽 탭 바, 보기 설정·더보기 하단 시트, 마우스오버 정보(data-tip)를 눌러서 보는 하단 시트,
  상세 창 전체 화면, 큰 터치 영역, 홈 화면에 추가(PWA).
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "docs")
s = open(os.path.join(D, "index.html"), encoding="utf-8", newline="").read()
t = s.replace("\r\n", "\n")


def rep(a, b):
    global t
    assert t.count(a) == 1, (t.count(a), a[:80])
    t = t.replace(a, b)


# ---------- 1) head ----------
rep('<meta name="viewport" content="width=device-width, initial-scale=1">',
    '''<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#f8f5ea">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Before KBO">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="manifest.json">
<link rel="icon" type="image/png" sizes="192x192" href="img/icons/icon-192.png">
<link rel="apple-touch-icon" href="img/icons/apple-touch-icon.png">''')

# ---------- 2) 헤더: 로고 + 투수/타자 + 설정 ----------
a = t.index('<header class="top">')
b = t.index("</header>") + len("</header>")
theme_btn = re.search(r'<button type="button" class="themebtn".*?</button>', t[a:b], re.S).group(0)
t = t[:a] + '''<header class="top">
  <div class="wrap">
    <a class="logo brand" href="#top" aria-label="Before KBO"><img src="img/logo.png" alt="Before KBO" width="110" height="19"></a>
    <nav aria-label="보기">
      <div class="seg" id="roleSeg"><button data-r="투수" class="on">투수</button><button data-r="타자">타자</button></div>
      <button type="button" class="setbtn" id="setBtn" aria-label="보기 설정"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h10M17 7h4M3 17h4M11 17h10"/><circle cx="15" cy="7" r="2.3"/><circle cx="9" cy="17" r="2.3"/></svg></button>
    </nav>
  </div>
</header>''' + t[b:]

# ---------- 3) 보기 설정 카드 -> 하단 시트 ----------
a = t.index('  <div class="tool" id="s0">')
b = t.index('  <div class="tabs" id="tabs"')
panel = t[a:b]
t = t[:a] + t[b:]
SEG = '<div class="seg" id="roleSeg"><button data-r="투수" class="on">투수</button><button data-r="타자">타자</button></div>\n      '
assert panel.count(SEG) == 1
panel = panel.replace(SEG, "")
panel = panel.replace('<div class="tool" id="s0">', "").replace('    <p class="eyebrow">설정</p>\n    <h2>보기 설정</h2>\n', "").rstrip()
assert panel.endswith("</div>")
panel = panel[:-len("</div>")].rstrip()          # 바깥 카드의 닫는 태그 제거
SHEET_HEAD = '<div class="sheethead"><div class="grab"></div><button type="button" class="sheetx" data-close aria-label="닫기">✕</button></div>'
sheets = f'''<div class="sheetwrap" id="setSheet" hidden><div class="sheetbg" data-close></div><div class="sheetpanel">{SHEET_HEAD}<div class="sheetbody" id="s0">
    <h3 class="sheettitle">보기 설정</h3>
{panel}
  </div></div></div>
<div class="sheetwrap" id="moreSheet" hidden><div class="sheetbg" data-close></div><div class="sheetpanel">{SHEET_HEAD}<div class="sheetbody">
    <div class="morelist">
      <button type="button" data-go="s6">구단별 <span class="mut">By Team</span></button>
      <button type="button" data-go="s4">검증 <span class="mut">Validation</span></button>
      <button type="button" data-go="s7">스카우팅 노트 <span class="mut">Reports</span></button>
      <div class="morerow"><span>화면 모드</span>{theme_btn}</div>
      <div class="morelinks"><a href="https://github.com/bylinercho/before_kbo" rel="noopener">GitHub</a><a href="https://baseballsavant.mlb.com/" rel="noopener">Baseball Savant</a><a href="https://mykbostats.com/" rel="noopener">MyKBO Stats</a><a href="https://github.com/chadwickbureau/register" rel="noopener">Chadwick Register</a><a href="index.html">웹 버전</a></div>
    </div>
  </div></div></div>
<div class="sheetwrap" id="sheet" hidden><div class="sheetbg" data-close></div><div class="sheetpanel">{SHEET_HEAD}<div class="sheetbody" id="sheetBody"></div></div></div>
<nav class="bnav" id="bnav" aria-label="메뉴">
  <button type="button" data-tab="s1"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg>사례</button>
  <button type="button" data-tab="s2"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 20V10M12 20V4M19 20v-7"/></svg>지표</button>
  <button type="button" data-tab="s3"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l8.5 6.2-3.2 10H6.7l-3.2-10z"/></svg>닮은 선수</button>
  <button type="button" data-tab="s8"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg>루머</button>
  <button type="button" data-tab="more"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.7" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.7" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.7" fill="currentColor" stroke="none"/></svg>더보기</button>
</nav>
'''
rep('<dialog id="dlg">', sheets + '<dialog id="dlg">')

# ---------- 4) 마우스오버 툴팁 -> 삭제(눌러서 하단 시트로 대체) ----------
a = t.index("/* ================= 그래프 마우스오버 툴팁 ================= */")
b = t.index("/* ================= 디자인 전환")
t = t[:a] + t[b:]

# ---------- 5) 탭 스크립트 -> 하단 탭 + 시트 ----------
a = t.index("/* ================= 챕터 탭 ================= */")
b = t.index('showTab("s1", false);') + len('showTab("s1", false);')
t = t[:a] + r'''/* ================= 앱형: 하단 탭 · 하단 시트 ================= */
const CHAPTERS = ["s1","s2","s6","s3","s4","s8","s7"];
const MAIN_TABS = ["s1","s2","s3","s8"];
CHAPTERS.forEach(id=> $(id).classList.add("chapter"));
function showTab(id, scroll){
  if (!CHAPTERS.includes(id)) id = "s1";
  CHAPTERS.forEach(c=> $(c).hidden = c!==id);
  document.querySelectorAll("#bnav button").forEach(b=>{
    const on = b.dataset.tab===id || (b.dataset.tab==="more" && !MAIN_TABS.includes(id));
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (scroll) scrollTo({top:0, behavior:"instant"});
  try { history.replaceState(null, "", "#"+id); } catch(e){}
}
document.addEventListener("click", e=>{
  const a = e.target.closest('a[href^="#s"]'); if (!a) return;
  const id = a.getAttribute("href").slice(1);
  if (CHAPTERS.includes(id)){ e.preventDefault(); showTab(id, true); }
});
const h0 = location.hash.slice(1); showTab(CHAPTERS.includes(h0) ? h0 : "s1", false);

/* 하단 시트: 열고 닫기. 열린 창(dialog) 위에도 보이게 호스트 안으로 옮긴다 */
function wrapOpen(el, host){
  if (host && el.parentNode !== host) host.appendChild(el);
  el.hidden = false; void el.offsetWidth; el.classList.add("on");
  document.documentElement.classList.add("noscroll");
}
function wrapClose(el){
  el.classList.remove("on");
  setTimeout(()=>{ if (!el.classList.contains("on")) el.hidden = true; if (!document.querySelector(".sheetwrap.on")) document.documentElement.classList.remove("noscroll"); }, 220);
}
document.addEventListener("click", e=>{
  if (e.target.closest("[data-close]")){ const w = e.target.closest(".sheetwrap"); if (w) wrapClose(w); return; }
  const go = e.target.closest("[data-go]"); if (go){ wrapClose($("moreSheet")); showTab(go.dataset.go, true); return; }
  if (e.target.closest(".sheetpanel .go")){ const w = e.target.closest(".sheetwrap"); if (w) wrapClose(w); }
});
document.addEventListener("keydown", e=>{ if (e.key==="Escape"){ const w = [...document.querySelectorAll(".sheetwrap.on")].pop(); if (w) wrapClose(w); } });
$("bnav").addEventListener("click", e=>{
  const b = e.target.closest("button[data-tab]"); if (!b) return;
  if (b.dataset.tab==="more") wrapOpen($("moreSheet")); else showTab(b.dataset.tab, true);
});
$("setBtn").addEventListener("click", ()=> wrapOpen($("setSheet")));
/* 아래로 끌어내려 닫기(머리 부분에서만) */
document.querySelectorAll(".sheetwrap").forEach(w=>{
  const p = w.querySelector(".sheetpanel"), hd = w.querySelector(".sheethead"); let y0 = null, dy = 0;
  hd.addEventListener("touchstart", e=>{ y0 = e.touches[0].clientY; dy = 0; }, {passive:true});
  hd.addEventListener("touchmove", e=>{ if (y0==null) return; dy = e.touches[0].clientY - y0; if (dy>0) p.style.transform = `translateY(${dy}px)`; }, {passive:true});
  hd.addEventListener("touchend", ()=>{ if (y0==null) return; p.style.transform = ""; if (dy>80) wrapClose(w); y0 = null; });
});

/* 마우스오버 정보(data-tip)는 눌러서 하단 시트로 본다 */
function openTip(t){
  const host = t.closest("dialog") || document.body;
  let h = `<div class="sheettip">${t.dataset.tip}</div>`;
  if (t.dataset.kind && t.dataset.key){
    h += `<button type="button" class="btn go" data-kind="${esc(t.dataset.kind)}" data-key="${esc(t.dataset.key)}" data-role="${esc(t.dataset.role||"")}">상세 보기</button>`;
  }
  $("sheetBody").innerHTML = h;
  wrapOpen($("sheet"), host);
}
document.addEventListener("click", e=>{
  const t = e.target.closest && e.target.closest("[data-tip]"); if (!t) return;
  if (t.closest("thead") && !t.closest(".timeline")) return;   // 정렬용 표 머리는 정렬 동작을 유지
  e.preventDefault(); e.stopPropagation(); openTip(t);
}, true);''' + t[b:]

# ---------- 6) 서비스워커 등록 ----------
rep("</body>", '''<script>if ("serviceWorker" in navigator && location.protocol !== "file:") addEventListener("load", ()=>navigator.serviceWorker.register("sw.js").catch(()=>{}));</script>
</body>''')

# ---------- 7) CSS ----------
CSS = r'''
<style>
/* ===== 앱형 레이아웃 (app.html 전용) ===== */
html{-webkit-tap-highlight-color:transparent;-webkit-text-size-adjust:100%}
html.noscroll,html.noscroll body{overflow:hidden}
body{padding-bottom:calc(66px + env(safe-area-inset-bottom))}
.hero,footer,.tabs{display:none !important}
html body .top .wrap{height:54px;flex-direction:row;padding-top:0;padding-bottom:0;gap:8px}
.top .wrap nav{display:flex;align-items:center;gap:8px}
.top .seg button{padding:8px 14px;min-height:36px}
.setbtn{width:40px;height:36px;display:grid;place-items:center;border:1px solid var(--line);background:transparent;color:var(--ink);cursor:pointer;border-radius:999px;padding:0}
html[data-theme="paper"] .setbtn{border:2px solid var(--rule);border-radius:0}
.setbtn svg,.bnav svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
input,select,textarea{font-size:16px}
main.tools{padding-top:6px}
.bnav{position:fixed;left:0;right:0;bottom:0;z-index:40;display:grid;grid-template-columns:repeat(5,1fr);background:var(--bg);border-top:2px solid var(--rule,var(--line));padding-bottom:env(safe-area-inset-bottom)}
.bnav button{font:inherit;font-size:11px;color:var(--muted);background:none;border:0;min-height:56px;padding:7px 2px 6px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;cursor:pointer;white-space:nowrap}
.bnav button[aria-selected="true"]{color:var(--accent);font-weight:700}
#cmpBar{bottom:calc(66px + env(safe-area-inset-bottom)) !important}
/* 하단 시트 */
.sheetwrap{position:fixed;inset:0;z-index:10000;display:flex;align-items:flex-end;justify-content:center}
.sheetwrap[hidden]{display:none}
.sheetbg{position:absolute;inset:0;background:rgba(0,0,0,.45);opacity:0;transition:opacity .2s}
.sheetwrap.on .sheetbg{opacity:1}
.sheetpanel{position:relative;width:min(560px,100%);max-height:82dvh;overflow:auto;background:var(--paper,var(--card));color:var(--ink);border:2px solid var(--rule,var(--line));border-bottom:0;border-radius:18px 18px 0 0;padding:0 20px calc(24px + env(safe-area-inset-bottom));transform:translateY(100%);transition:transform .22s ease;overscroll-behavior:contain}
.sheetwrap.on .sheetpanel{transform:none}
.sheethead{position:sticky;top:0;z-index:2;background:var(--paper,var(--card));padding:10px 0 8px;touch-action:none;margin:0 -20px;padding-left:20px;padding-right:20px}
.grab{width:46px;height:5px;border-radius:3px;background:var(--line);margin:0 auto}
.sheetx{position:absolute;right:10px;top:4px;width:40px;height:36px;border:0;background:none;color:var(--muted);font-size:18px;cursor:pointer}
.sheettitle{margin:4px 0 12px;font-size:17px}
.sheettip{font-size:15.5px;line-height:1.65;padding:6px 0 2px}
.sheettip .mut,.morelist .mut{color:var(--muted);font-size:13px}
.sheetpanel .go{margin-top:14px;width:100%;text-align:center;min-height:46px}
.morelist>button{display:flex;justify-content:space-between;align-items:center;width:100%;min-height:52px;border:0;border-bottom:1px solid var(--line);background:none;font:inherit;font-size:16px;color:var(--ink);text-align:left;cursor:pointer;padding:0 2px}
.morerow{display:flex;justify-content:space-between;align-items:center;min-height:56px;border-bottom:1px solid var(--line);font-size:16px}
.morelinks{display:flex;flex-wrap:wrap;gap:6px 18px;padding-top:14px;font-size:13.5px}
.morelinks a{color:var(--muted)}
#s0 .row{display:flex;flex-direction:column;align-items:stretch;gap:12px}
#s0 .row label{display:flex;justify-content:space-between;align-items:center;gap:10px}
/* 상세 창은 전체 화면 */
html[data-theme] dialog#dlg,html[data-theme] dialog#cmpDlg{width:100vw !important;max-width:100vw !important;height:100dvh !important;max-height:100dvh !important;margin:0 !important;border:0 !important;border-radius:0 !important;box-shadow:none}
.dlgin{padding:0 16px calc(32px + env(safe-area-inset-bottom))}
.dlghead{position:sticky;top:0;z-index:5;background:var(--card);margin:0 -16px 12px;padding:12px 16px;border-bottom:1px solid var(--line)}
.close{min-height:40px;padding:6px 16px}
/* 손가락으로 누르기 쉬운 크기 */
.mate{margin-left:0;padding:8px 3px}
.mi{height:22px}
.timeline{width:100%}
.timeline td.l{white-space:normal;word-break:keep-all;overflow-wrap:anywhere;line-height:1.35}
.timeline td.l .note{display:block}
.timeline td.mates{white-space:normal;min-width:76px}
.dlghead button,.close{white-space:nowrap}
.more{padding:0 6px}
tr.clickable td,.rep,.hrow{min-height:44px}
@media (max-width:820px){
  .wrap{padding:0 10px}
  html[data-theme="paper"] .tool{padding:18px 12px 18px 28px;margin:14px 0}
  html[data-theme="paper"] .tool::before,html[data-theme="paper"] .tool::after{left:8px;width:13px;height:13px}
  .tablewrap.tall{max-height:none !important}
  .tool .row select,.tool .row input[type=search]{max-width:100%;min-width:0}
  /* 글자를 확 줄인다: 본문·상세 창·시트 안쪽만 78%로(상단 바·하단 탭은 그대로) */
  main.tools,.dlgin,.sheetbody{zoom:.78}
  th,td{padding:6px 5px}
  th{font-size:11px;letter-spacing:0}
  .tablewrap td:first-child{white-space:nowrap;min-width:0}
  .tablewrap td:first-child .en{display:block;font-size:10.5px}
  .tablewrap td:first-child span[style*="cursor:help"]{display:none}   /* 눌러도 안 열리는 ⓘ(마우스오버용) */
}
@media (min-width:821px){ body{padding-bottom:0} .bnav{display:none} .top .wrap{max-width:1080px} .sheetwrap{align-items:center} .sheetpanel{border-radius:14px;border-bottom:2px solid var(--rule,var(--line));max-height:80dvh} }
</style>
</head>'''
rep("</head>", CSS)

open(os.path.join(D, "app.html"), "w", encoding="utf-8", newline="").write(t)

# ---------- 8) manifest, 서비스워커 ----------
manifest = {
    "name": "Before KBO", "short_name": "Before KBO",
    "description": "입단 전 5년 기록으로 보는 KBO 외국인 선수",
    "lang": "ko", "start_url": "app.html", "scope": "./", "display": "standalone",
    "background_color": "#f8f5ea", "theme_color": "#f8f5ea",
    "icons": [
        {"src": "img/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "img/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "img/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}
open(os.path.join(D, "manifest.json"), "w", encoding="utf-8").write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

sw = r'''// tools/17_make_app.py 가 만든 파일. 앱형 화면(app.html)을 오프라인에서도 열 수 있게 자료를 저장해 둔다.
// 방식: 인터넷이 되면 항상 최신을 받고(받은 것을 저장), 안 되면 저장해 둔 것을 쓴다. index.html 은 건드리지 않는다.
const V = "bk-app-v1";
const CORE = ["app.html", "theme-paper.css", "data.js", "awards.js", "rumors.js", "reports.js", "careers.js", "manifest.json",
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
'''
open(os.path.join(D, "sw.js"), "w", encoding="utf-8").write(sw)
print("app.html", len(t), "chars | manifest.json, sw.js 저장")
