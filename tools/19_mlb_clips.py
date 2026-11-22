"""19단계: 선수가 실제로 던지거나 치는 가장 최근 MLB 공식 하이라이트 클립을 찾아 data/videos.csv 에 넣는다.

실행:  python -I tools/19_mlb_clips.py "Zac Gallen" "Jose Urquidy"      이름으로 지정
       python -I tools/19_mlb_clips.py --rumors                          docs/rumors.js 의 선수 전부
       (옵션) --dry   파일은 건드리지 않고 찾은 결과만 보여 준다

방식(MLB Stats API, 공식·무료):
  1) 이름으로 선수 번호를 찾는다(현역·MLB 경력이 있는 사람).
  2) 시즌 경기 기록(gameLog)에서 최근 경기부터 거꾸로 훑는다(올해, 없으면 지난해).
  3) 경기 하이라이트(game/{경기번호}/content)에서 클립 이름이 선수 이름으로 시작하는 것을 찾는다.
     투수는 삼진 클립을 우선, 타자는 홈런 클립을 우선한다. 처음 찾은 경기(가장 최근)에서 멈춘다.
  4) https://www.mlb.com/video/<slug> 주소를 videos.csv 에 쓴다(채널=MLB, 제목=클립 제목, 업로드일=클립 날짜).
MLB 에 클립이 없는 선수(마이너, 해외 리그)는 건너뛰므로 그 선수는 화면에서 검색 링크만 보인다.
"""
import csv, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "videos.csv")
API = "https://statsapi.mlb.com/api/v1"
YEARS = [2026, 2025]
MAX_GAMES = 14


def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (before-kbo personal project)"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def slugify(n):
    n = "".join(c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-")


def find_player(name):
    best = None
    for p in get(f"{API}/people/search?names={urllib.parse.quote(name)}&sportIds=1").get("people", []):
        if slugify(p.get("fullName", "")) != slugify(name):
            continue
        if p.get("mlbDebutDate") and (best is None or p.get("active")):
            best = p
    return best


def latest_clip(p):
    pid, name = p["id"], p["fullName"]
    pos = (p.get("primaryPosition") or {}).get("type", "")
    group = "pitching" if pos == "Pitcher" else "hitting"
    ns = slugify(name) + "-"
    fallback = None
    for yr in YEARS:
        gl = get(f"{API}/people/{pid}/stats?stats=gameLog&group={group}&season={yr}&sportId=1")
        splits = gl["stats"][0]["splits"] if gl.get("stats") else []
        for s in sorted(splits, key=lambda x: x["date"], reverse=True)[:MAX_GAMES]:
            items = get(f"{API}/game/{s['game']['gamePk']}/content").get("highlights", {}).get("highlights", {}).get("items", [])
            def kind(it):
                """이 클립에서 선수가 하는 일을 점수로: 3=삼진을 잡음/홈런, 2=안타, 1=그 밖(맞는 장면 등), 0=제외"""
                slug, head = it.get("slug") or "", slugify(it.get("headline", ""))
                if "capture-review" in slug:
                    return 0
                if group == "pitching":
                    if head.startswith(ns) and (" fans " in " " + it.get("headline", "").lower() + " " or "k-s" in head or "strikes" in head or "strikeout" in head):
                        return 3
                    if slug.startswith(ns) and any(k in slug for k in ("strikes-out", "flies-out", "grounds-out", "lines-out", "pops-out", "walks")):
                        return 0                    # 투수가 타석에 선 장면
                    if head.startswith(ns) or slug.startswith(ns):
                        return 1
                    return 0
                if not slug.startswith(ns):
                    return 0
                if any(k in slug for k in ("homers", "home-run")):
                    return 3
                if any(k in slug for k in ("singles", "doubles", "triples", "in-play-run")):
                    return 2
                if any(k in slug for k in ("strikes-out", "flies-out", "grounds-out", "lines-out", "pops-out", "walks")):
                    return 0
                return 1
            scored = sorted(((kind(it), it) for it in items), key=lambda x: -x[0])
            if scored and scored[0][0] >= 2:
                it = scored[0][1]
                return {"url": "https://www.mlb.com/video/" + it["slug"], "title": it.get("headline", it["slug"]), "date": (it.get("date") or s["date"])[:10]}
            if scored and scored[0][0] == 1 and fallback is None:
                it = scored[0][1]
                fallback = {"url": "https://www.mlb.com/video/" + it["slug"], "title": it.get("headline", it["slug"]), "date": (it.get("date") or s["date"])[:10]}
        if fallback:
            return fallback
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if "--rumors" in sys.argv:
        t = open(os.path.join(ROOT, "docs", "rumors.js"), encoding="utf-8").read()
        args += re.findall(r'name:"([^"]+)"', t)
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    fields = ["영문명", "주소", "채널", "제목", "업로드일"]
    for r in rows:                                   # 예전 형식(영상ID)을 주소로 바꾼다
        if not r.get("주소"):
            r["주소"] = "https://www.youtube.com/watch?v=" + r.get("영상ID", "")
    byname = {slugify(r["영문명"]): r for r in rows}
    for name in args:
        p = find_player(name)
        if not p:
            print("선수를 못 찾음:", name); continue
        c = latest_clip(p)
        if not c:
            print("클립 없음:", name, "(", p.get("currentTeam", {}).get("name", ""), ")"); continue
        print(c["date"], name, "|", c["title"][:60], "|", c["url"])
        byname[slugify(name)] = {"영문명": name, "주소": c["url"], "채널": "MLB", "제목": c["title"], "업로드일": c["date"]}
        time.sleep(0.3)
    if not dry:
        with open(CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(byname.values())
        print("저장:", CSV, len(byname), "명")


if __name__ == "__main__":
    main()
