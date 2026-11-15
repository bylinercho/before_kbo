"""10단계: 연도·레벨별 리그 평균(환경 보정 기준)을 MLB 공식 Stats API에서 받는다.

실행:  python -I tools/10_league_context.py
결과:  data/raw/league/<연도>_<레벨>.json   받은 원본 (git 제외)
       data/league_rates.csv                연도·레벨별 리그 평균 비율

받는 것: 2010~2026 시즌, 레벨 MLB·AAA·AA·A+·A 의 팀별 시즌 기록을 합산한 리그 합계.
         트리플A(sportId 11)는 MLB 시스템이 멕시칸 리그 팀을 섞어 두었으므로 팀의 리그 이름이
         "Mexican League"인 팀은 뺀다 (07번에서 선수 기록을 "MEX"로 따로 둔 것과 같은 기준).

쓰임: 08번이 선수 기록을 "같은 해·같은 레벨 리그 평균 대비 지수(리그 평균=100)"로 바꾼다.
      - 투수: 삼진%, 볼넷%, 홈런%(상대 타자 대비), ERA
      - 타자: 삼진%, 볼넷%, 홈런%(타석 대비), ISO, 타율
한계: 같은 레벨 안에서의 상대 위치이다. 레벨 사이의 실력 차(트리플A 평균 선수 vs MLB 평균 선수)는 보정하지 않는다.

규칙: 호출 사이 1초 쉰다. 이미 받은 원본은 다시 받지 않는다.
"""
import json
import os
import sys
import time

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

LEVELS = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A"}
YEARS = range(2010, 2027)
OUT = "data/raw/league"
H = {"User-Agent": "Mozilla/5.0 (research script)"}
API = "https://statsapi.mlb.com/api/v1"


def get(path, params):
    r = requests.get(f"{API}/{path}", params=params, headers=H, timeout=120)
    r.raise_for_status()
    return r.json()


def outs_of(ip):
    whole, _, frac = str(ip).partition(".")
    return int(whole) * 3 + (int(frac) if frac else 0)


def fetch(year, sport):
    path = os.path.join(OUT, f"{year}_{LEVELS[sport]}.json")
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    data = get("teams/stats", {"season": year, "group": "pitching,hitting", "stats": "season", "sportIds": sport})
    mex = set()
    if sport == 11:
        for t in get("teams", {"sportId": 11, "season": year}).get("teams", []):
            if t.get("league", {}).get("name") == "Mexican League":
                mex.add(t["id"])
        time.sleep(1)
    out = {"mex": sorted(mex), "stats": data.get("stats", [])}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    time.sleep(1)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for year in YEARS:
        for sport, level in LEVELS.items():
            try:
                d = fetch(year, sport)
            except Exception as e:
                print(year, level, "실패", repr(e)[:100], flush=True)
                continue
            mex = set(d["mex"])
            p = {k: 0 for k in ["bf", "so", "bb", "hr", "er", "outs"]}
            h = {k: 0 for k in ["pa", "ab", "h", "so", "bb", "hr", "tb"]}
            teams = 0
            for blk in d["stats"]:
                grp = blk["group"]["displayName"]
                for s in blk["splits"]:
                    if s.get("team", {}).get("id") in mex:
                        continue
                    st = s["stat"]
                    if grp == "pitching":
                        teams += 1
                        p["bf"] += st.get("battersFaced", 0); p["so"] += st.get("strikeOuts", 0)
                        p["bb"] += st.get("baseOnBalls", 0); p["hr"] += st.get("homeRuns", 0)
                        p["er"] += st.get("earnedRuns", 0); p["outs"] += outs_of(st.get("inningsPitched", "0.0"))
                    else:
                        h["pa"] += st.get("plateAppearances", 0); h["ab"] += st.get("atBats", 0)
                        h["h"] += st.get("hits", 0); h["so"] += st.get("strikeOuts", 0)
                        h["bb"] += st.get("baseOnBalls", 0); h["hr"] += st.get("homeRuns", 0)
                        h["tb"] += st.get("totalBases", 0)
            if p["bf"] == 0 or h["pa"] == 0:
                print(year, level, "자료 없음", flush=True)
                continue
            rows.append({
                "season": year, "level": level, "teams": teams,
                "p_k": p["so"] / p["bf"] * 100, "p_bb": p["bb"] / p["bf"] * 100, "p_hr": p["hr"] / p["bf"] * 100,
                "p_era": p["er"] * 27 / p["outs"],
                "h_k": h["so"] / h["pa"] * 100, "h_bb": h["bb"] / h["pa"] * 100, "h_hr": h["hr"] / h["pa"] * 100,
                "h_iso": (h["tb"] - h["h"]) / h["ab"], "h_avg": h["h"] / h["ab"],
                "bf": p["bf"], "pa": h["pa"],
            })
        print(year, "완료", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv("data/league_rates.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print("=" * 70)
    print("연도·레벨 조합:", len(df))
    print(df[df["level"].isin(["MLB", "AAA"])][["season", "level", "teams", "p_k", "p_bb", "p_hr", "p_era", "h_iso", "h_avg"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
