"""3단계: 시즌별 스탯캐스트(선수별 묶음)를 받고, 2026 후보 풀을 만든다.

실행:  python -I tools/03_download_seasons.py
결과:  data/raw/seasons/ 아래에 CSV (이미 있는 파일은 건너뜀. 다시 받으려면 파일을 지운다)
       data/candidates_2026.csv  2026 후보 풀 (트리플A·MLB를 합쳐서 본 선수 목록)

받는 것: 트리플A 투수·타자(2023~2026), MLB 투수·타자(2015~2026)
         (트리플A 스탯캐스트는 2023년부터, MLB 스탯캐스트 지표는 2015년부터 있다. 2026-11-15 확인)

후보 풀 (2026-11-15 변경: 트리플A만 보던 것을 MLB까지 넓힘)
- 2026 시즌에 트리플A와 MLB 기록을 "합쳐서" 투수는 공 500개, 타자는 200타석 이상인 선수.
  트리플A↔MLB를 오간 선수, MLB에서만 뛴 선수도 들어간다.
- 소속 구분: "AAA만" / "MLB만" / "AAA·MLB 오감"
- 스탯캐스트 지표는 2026년에 공을 더 많이 본 쪽(트리플A 또는 MLB) 기록을 쓴다(sc_level, sc_n).
- 이 목록은 스탯캐스트 기준이라 "2026년에 미국에서 뛴 선수"만 잡힌다. KBO·NPB 등에서 뛴 선수는 없다.
"""
import io
import os
import sys
import time

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://baseballsavant.mlb.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (research script; contact: local)"}
OUT = "data/raw/seasons"
SEASONS = {"AAA": [2023, 2024, 2025, 2026],            # 트리플A 스탯캐스트는 2023년부터
           "MLB": list(range(2015, 2027))}              # MLB 스탯캐스트 지표는 2015년부터 (2026-11-15 확인: 2012년엔 구속·삼진·볼넷만)
POOL_YEAR = 2026
SC = {"pitcher": ["velocity", "k_percent", "bb_percent", "swing_miss_percent", "hardhit_percent", "xwoba",
                  "launch_angle", "release_extension", "arm_angle"],
      "batter": ["launch_speed", "hardhit_percent", "barrels_per_bbe_percent", "xwoba", "k_percent",
                 "bb_percent", "swing_miss_percent", "launch_angle"]}
ROLE_KR = {"pitcher": "투수", "batter": "타자"}


def url(level, role, year):
    if level == "AAA":  # 01번에서 확인한 형식
        return (f"{BASE}/statcast-search-minors/csv?hfSea={year}%7C&hfLevel=AAA%7C&player_type={role}"
                "&group_by=name&min_pitches=100&minors=true")
    # MLB: 일반 스탯캐스트 검색의 같은 묶음 방식 (정규시즌만).
    # 2026-11-15 확인: type=details 를 붙이면 0행이 온다. 빼면 선수별 77칸이 온다.
    return (f"{BASE}/statcast_search/csv?hfSea={year}%7C&hfGT=R%7C&player_type={role}"
            "&group_by=name&min_pitches=100")


def download():
    os.makedirs(OUT, exist_ok=True)
    report = []
    for level in ["AAA", "MLB"]:
        for role in ["pitcher", "batter"]:
            for year in SEASONS[level]:
                name = f"{level}_{role}_{year}.csv"
                path = os.path.join(OUT, name)
                if os.path.exists(path):
                    report.append((name, "이미 있음", "", ""))
                    continue
                try:
                    r = requests.get(url(level, role, year), headers=HEADERS, timeout=180)
                    r.raise_for_status()
                    df = pd.read_csv(io.BytesIO(r.content))
                    if len(df) == 0:  # 빈 파일은 저장하지 않는다 (다음 실행 때 건너뛰지 않도록)
                        raise ValueError("0행 (주소가 틀렸을 수 있음)")
                    with open(path, "wb") as f:
                        f.write(r.content)
                    report.append((name, r.status_code, len(df), len(df.columns)))
                except Exception as e:
                    report.append((name, "실패", repr(e)[:120], ""))
                print(report[-1], flush=True)
                time.sleep(5)
    print("=" * 70)
    for row in report:
        print(row)


def build_pool():
    rows = []
    for role in ["pitcher", "batter"]:
        frames = []
        for level in ["AAA", "MLB"]:
            path = os.path.join(OUT, f"{level}_{role}_{POOL_YEAR}.csv")
            d = pd.read_csv(path, encoding="utf-8-sig")
            d["lv"] = level
            frames.append(d)
        d = pd.concat(frames, ignore_index=True)
        for pid, g in d.groupby("player_id"):
            a, m = g[g["lv"] == "AAA"], g[g["lv"] == "MLB"]
            total_p, total_pa = int(g["total_pitches"].sum()), int(g["pa"].sum())
            if (role == "pitcher" and total_p < 500) or (role == "batter" and total_pa < 200):
                continue
            best = g.sort_values("total_pitches").iloc[-1]  # 공을 더 많이 본 쪽 기록을 스탯캐스트 보조 지표로 쓴다
            row = {"역할": ROLE_KR[role], "player_id": int(pid), "player_name": g["player_name"].iloc[0],
                   "total_pitches": total_p, "pa": total_pa,
                   "AAA_공수": int(a["total_pitches"].sum()), "MLB_공수": int(m["total_pitches"].sum()),
                   "AAA_타석": int(a["pa"].sum()), "MLB_타석": int(m["pa"].sum()),
                   "소속": "AAA·MLB 오감" if len(a) and len(m) else ("AAA만" if len(a) else "MLB만"),
                   "sc_level": best["lv"], "sc_n": int(best["total_pitches"])}
            for f in SC[role]:
                row[f] = best[f]
            rows.append(row)
    pool = pd.DataFrame(rows)
    pool.to_csv("data/candidates_2026.csv", index=False, encoding="utf-8-sig")
    print("=" * 70)
    print("후보 풀:", len(pool), "명")
    print(pool.groupby(["역할", "소속"]).size().to_string())


if __name__ == "__main__":
    download()
    build_pool()
