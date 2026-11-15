"""13단계: 선수별 부상자 명단(IL) 이력을 MLB 공식 Stats API의 선수 이동 기록에서 뽑는다.

실행:  python -I tools/13_injuries.py
입력:  data/cohort_profiles.csv (지난 사례 mlbam), data/candidates_profiles.csv (2026 후보 player_id)
결과:  data/raw/transactions/chunk_<n>.json   받은 원본 (git 제외)
       data/il_stints.csv                       부상자 명단 등재 1건당 한 줄: id, 시작, 복귀, 일수, 명단 종류(7/10/15/60일), 부상 내용, 복귀 기록 없음 여부

확인한 사실 (2026-11-15)
- 스탯캐스트(Baseball Savant) 자료에는 부상 칸이 없다. 부상자 명단 기록은 MLB 공식 API의 선수 이동 기록(transactions)에 있다.
- MLB 로스터 선수는 부상 내용(예: "Right elbow inflammation", "Tommy John surgery")까지 나온다.
  마이너 소속일 때는 "placed ... on the 7-day injured list"만 있고 부상 내용이 없는 경우가 많다. 마이너 기록은 빠졌을 수 있다.

계산 규칙
- "placed ... on the N-day injured list" = 등재(소급 날짜 retroactive to 가 있으면 그 날짜), "activated/reinstated ... from the injured list" = 복귀.
  명단 사이 이동("transferred 10-day → 60-day")이나 같은 부상으로 다시 등재된 것은 한 건으로 이어 붙인다.
- 복귀 기록이 없으면 그 해 10월 31일까지(2026년은 데이터 수집일까지)로 보고 "open"으로 표시한다.
- 일수 = 등재일~복귀일. 비시즌 로스터 정리 때문에 실제 결장 일수보다 길게 잡힐 수 있다.

규칙: 선수 40명씩 묶어 요청하고 사이에 2초 쉰다. 이미 받은 묶음은 다시 받지 않는다.
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

OUT = "data/raw/transactions"
H = {"User-Agent": "Mozilla/5.0 (research script)"}
END = date(2026, 11, 15)
PLACED = re.compile(r"placed .*? on the (\d+)-day injured list(?: retroactive to ([A-Za-z]+ \d{1,2}, \d{4}))?\.?\s*(.*)$", re.I | re.S)
BACK = re.compile(r"(activated|reinstated|returned) .*?from the (?:\d+-day )?injured list", re.I)


def pdate(s):
    return datetime.strptime(s, "%B %d, %Y").date()


def fetch(ids, k):
    path = os.path.join(OUT, f"chunk_{k}.json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    r = requests.get("https://statsapi.mlb.com/api/v1/transactions", headers=H, timeout=180,
                     params={"playerId": ",".join(map(str, ids)), "startDate": "2010-01-01", "endDate": "2026-11-15"})
    r.raise_for_status()
    tx = [{"id": t["person"]["id"], "date": t["date"], "desc": t.get("description", "")}
          for t in r.json().get("transactions", []) if "injured list" in t.get("description", "").lower()]
    json.dump(tx, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    time.sleep(2)
    return tx


def stints_of(pid, tx):
    ev = sorted([t for t in tx if t["id"] == pid], key=lambda t: t["date"])
    out, cur = [], None
    for t in ev:
        d0 = datetime.strptime(t["date"][:10], "%Y-%m-%d").date()
        m = PLACED.search(t["desc"])
        if m and "transferred" not in t["desc"].lower().split("placed")[0]:
            start = pdate(m.group(2)) if m.group(2) else d0
            text = re.sub(r"\s+", " ", m.group(3)).strip(" .")
            if cur is None:
                cur = {"start": start, "kind": int(m.group(1)), "text": text}
            else:  # 이미 열려 있는 명단에서 다른 명단으로 옮긴 경우: 이어 붙임
                cur["kind"] = max(cur["kind"], int(m.group(1)))
                if text and not cur["text"]:
                    cur["text"] = text
        elif BACK.search(t["desc"]) and cur is not None:
            cur["end"], cur["open"] = d0, 0
            out.append(cur)
            cur = None
        elif "transferred" in t["desc"].lower() and cur is not None:
            m2 = re.search(r"to the (\d+)-day injured list", t["desc"], re.I)
            if m2:
                cur["kind"] = max(cur["kind"], int(m2.group(1)))
            m3 = re.search(r"injured list\.\s*(.*)$", t["desc"], re.S)
            if m3 and not cur["text"]:
                cur["text"] = re.sub(r"\s+", " ", m3.group(1)).strip(" .")
    if cur is not None:  # 복귀 기록 없음
        cur["end"] = min(date(cur["start"].year, 10, 31), END) if cur["start"].year < END.year else END
        cur["open"] = 1
        if cur["end"] < cur["start"]:
            cur["end"] = cur["start"]
        out.append(cur)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    ids = set(pd.read_csv("data/cohort_profiles.csv")["mlbam"].dropna().astype(int)) | set(pd.read_csv("data/candidates_profiles.csv")["player_id"].astype(int))
    ids = sorted(ids)
    print("선수", len(ids), "명")
    tx = []
    for k in range(0, len(ids), 40):
        tx += fetch(ids[k:k + 40], k // 40)
        print(f"{min(k + 40, len(ids))}/{len(ids)}명 처리", flush=True)
    rows = []
    for pid in ids:
        for s in stints_of(pid, tx):
            rows.append({"id": pid, "start": s["start"].isoformat(), "end": s["end"].isoformat(), "days": (s["end"] - s["start"]).days,
                         "kind": s["kind"], "text": s["text"], "open": s["open"]})
    df = pd.DataFrame(rows)
    df.to_csv("data/il_stints.csv", index=False, encoding="utf-8-sig")
    print("=" * 70)
    print("부상자 명단 등재", len(df), "건 / 선수", df["id"].nunique(), "명 (전체 선수", len(ids), "명)")
    print("일수 중앙값", df["days"].median(), "/ 복귀 기록 없음", int(df["open"].sum()), "건 / 내용 있는 건", int((df["text"] != "").sum()))
    print("토미존 언급", int(df["text"].str.contains("tommy john", case=False).sum()), "건")


if __name__ == "__main__":
    main()
