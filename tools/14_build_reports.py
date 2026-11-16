"""14단계: 방문자 스카우팅 노트를 화면용 자료(docs/reports.js)로 만든다.

흐름
  1. Google Form 응답 시트를 CSV로 내려받아 data/reports_submitted.csv 로 저장한다.
  2. 운영자가 검수한 행의 '승인' 칸에 O (또는 Y, 승인)를 적는다. 비어 있으면 올라가지 않는다.
  3. python -I tools/14_build_reports.py

기대하는 열 이름(폼 질문 제목과 같게): 타임스탬프, 선수 코드, 선수 이름, 한줄 평, 강점, 우려점, 근거 링크, 닉네임, 승인
  선수 코드 형식: "투수|cand|12345" (역할|cand 또는 past|player_id 또는 mykbo_id) — 폼이 사전 입력으로 채운다.

출력: docs/reports.js  (window.REPORTS = [...])  승인된 글만, 길이를 잘라서 담는다.
"""
import csv, json, os, re, sys

SRC = "data/reports_submitted.csv"
OUT = "docs/reports.js"
LIMIT = {"one": 140, "pro": 300, "con": 300, "nick": 20, "name": 60}
OK = {"o", "y", "yes", "승인", "ㅇ"}


def clip(s, n):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s[:n]


def main():
    if not os.path.exists(SRC):
        print(f"{SRC} 없음 - 빈 목록으로 {OUT} 를 만듭니다.")
        rows = []
    else:
        with open(SRC, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

    out, skipped = [], 0
    for r in rows:
        if (r.get("승인") or "").strip().lower() not in OK:
            skipped += 1
            continue
        code = (r.get("선수 코드") or "").strip().split("|")
        if len(code) != 3 or code[0] not in ("투수", "타자") or code[1] not in ("cand", "past") or not code[2]:
            print("건너뜀(선수 코드 형식 오류):", (r.get("선수 코드") or "")[:40])
            skipped += 1
            continue
        one = clip(r.get("한줄 평"), LIMIT["one"])
        if not one:
            skipped += 1
            continue
        link = (r.get("근거 링크") or "").strip()
        if not re.match(r"^https?://", link, re.I):
            link = ""
        out.append({
            "role": code[0], "kind": code[1], "id": code[2],
            "name": clip(r.get("선수 이름"), LIMIT["name"]),
            "one": one,
            "pro": clip(r.get("강점"), LIMIT["pro"]),
            "con": clip(r.get("우려점"), LIMIT["con"]),
            "link": link[:300],
            "nick": clip(r.get("닉네임"), LIMIT["nick"]) or "익명",
            "date": (r.get("타임스탬프") or "")[:10].replace("/", "-").replace(".", "-").strip("- "),
        })

    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.REPORTS = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
    print(f"승인 {len(out)}건 반영, 제외 {skipped}건 -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
