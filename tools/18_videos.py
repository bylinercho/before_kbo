"""18단계: 선수별 대표 유튜브 영상 목록(data/videos.csv)을 화면용 docs/videos.js 로 만든다.

실행:  python -I tools/18_videos.py            목록을 읽어 docs/videos.js 생성
       python -I tools/18_videos.py --check    각 영상이 아직 살아 있는지(공개 oEmbed) 확인만 한다

data/videos.csv 열:  영문명, 주소(유튜브 watch 주소 또는 mlb.com/video 주소), 채널, 제목, 업로드일(YYYY-MM-DD, 화면에 같이 보임)
- 영문명은 화면의 선수 영문 이름과 같아야 한다(대소문자 무시). 한 선수당 한 줄.
- 영상을 바꾸려면 그 줄의 영상ID·채널·제목만 고치고 이 스크립트를 다시 돌린다. 없는 선수는 화면에서 검색 링크만 보인다.
- 원칙: 그 선수가 실제로 던지거나 치는 가장 최근 영상을 쓴다. MLB 선수는 tools/19_mlb_clips.py 가 공식 클립을 자동으로 찾아 넣는다(업로드일로 확인). 새 영상이 올라오면 줄을 바꾼다.
- 영상은 사람이 검색해서 고른다. 제목·채널은 oEmbed 로 확인한 값을 적는다(--check 로 삭제된 영상을 찾는다).
"""
import csv, json, os, re, sys, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "videos.csv"), encoding="utf-8-sig")))
for r in rows:
    if not (r.get("주소") or "").strip():
        r["주소"] = "https://www.youtube.com/watch?v=" + (r.get("영상ID") or "").strip()
bad = [r["영문명"] for r in rows if not re.match(r"https://(www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}|www\.mlb\.com/video/[a-z0-9-]+)$", r["주소"].strip())]
if bad:
    sys.exit(f"주소 형식이 이상한 줄: {bad}")

if "--check" in sys.argv:
    for r in rows:
        u = r["주소"].strip()
        try:
            if "youtube.com" in u:
                d = json.load(urllib.request.urlopen("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(u, safe=""), timeout=15))
                print("OK  ", r["영문명"], "|", d["author_name"], "|", d["title"][:60])
            else:
                code = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).status
                print("OK  " if code == 200 else "확인 필요", r["영문명"], "| MLB", code)
        except Exception as e:
            print("확인 필요", r["영문명"], u, e)
    sys.exit()

import unicodedata
norm = lambda x: "".join(c for c in unicodedata.normalize("NFD", x.strip().lower()) if unicodedata.category(c) != "Mn")   # 악센트 제거(화면과 같은 규칙)
V = {norm(r["영문명"]): {"u": r["주소"].strip(), "ch": r["채널"].strip(), "t": r["제목"].strip(), "d": (r.get("업로드일") or "").strip()} for r in rows}
with open(os.path.join(ROOT, "docs", "videos.js"), "w", encoding="utf-8") as f:
    f.write("// tools/18_videos.py 가 만든 파일. 직접 고치지 않는다(원본: data/videos.csv). 키는 선수 영문 이름(소문자)\nwindow.VIDEOS = ")
    json.dump(V, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";\n")
print("docs/videos.js:", len(V), "명")
