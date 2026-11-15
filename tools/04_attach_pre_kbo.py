"""4단계: 동명이인을 정리하고, 신규 영입 선수의 "KBO 오기 전" 스탯캐스트 기록을 붙인다.

실행:  python tools/04_attach_pre_kbo.py
입력:  data/kbo_foreign_matched.csv, data/raw/seasons/*.csv (03번 결과)
결과:  data/kbo_foreign_resolved.csv  명단 + 정리된 선수 번호 + 직전 시즌 요약
       data/kbo_pre_kbo_stats.csv     신규 선수의 KBO 오기 전 시즌별 기록 (선수·시즌·레벨마다 한 줄)

규칙
- 동명이인: 후보 번호 가운데 "KBO 시즌보다 앞선 해에, 자기 포지션(투수/타자) 기록이 있는" 사람이
  딱 한 명일 때만 그 번호로 정한다. 2명 이상이면 KBO에서 뛴 해에 미국 기록이 있는 후보를 빼고,
  그래도 한 명으로 좁혀지지 않으면 비워 두고 "확인 필요"로 적는다.
- 직전 시즌: KBO 시즌보다 앞선 해 가운데 기록이 있는 가장 최근 해.
  받은 자료가 2023년부터라 그 이전은 알 수 없다. 일본 등 다른 리그에서 뛴 해는 여기 없다.
- 기록은 "신규" 선수만 붙인다. (재계약·이적·복귀 선수는 직전 해에 KBO에 있었거나 첫해가 아니다)
- 자료에 있는 선수는 그 해 공 100개 이상(min_pitches=100)인 선수뿐이다.
"""
import glob
import os

import pandas as pd

RAW = "data/raw/seasons"
ROLE = {"투수": "pitcher", "타자": "batter"}


def load_raw():
    frames = []
    for path in sorted(glob.glob(os.path.join(RAW, "*.csv"))):
        level, role, year = os.path.basename(path)[:-4].split("_")
        df = pd.read_csv(path, encoding="utf-8-sig")
        df.insert(0, "기록시즌", int(year))
        df.insert(1, "레벨", level)
        df.insert(2, "역할", role)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main():
    raw = load_raw()
    players = pd.read_csv("data/kbo_foreign_matched.csv", dtype=str).fillna("")

    out_rows, stat_rows = [], []
    for _, p in players.iterrows():
        p = p.to_dict()
        season = int(p["시즌"])
        role = ROLE.get(p["포지션"], "")
        before = raw[(raw["기록시즌"] < season) & (raw["역할"] == role)]

        pid, how = p["mlbam"], ""
        if pid:
            how = "02번에서 확정"
        elif p["후보번호"]:
            cands = [c for c in p["후보번호"].split("|") if c]
            hit = [c for c in cands if (before["player_id"] == int(c)).any()]
            # 후보가 여럿 남으면: KBO에서 뛴 해에 미국(MLB·트리플A) 기록이 있는 후보는 뺀다
            same_year = raw[(raw["기록시즌"] == season) & (raw["역할"] == role)]
            away = [c for c in hit if not (same_year["player_id"] == int(c)).any()]
            if len(hit) == 1:
                pid, how = hit[0], "동명이인 정리(직전 기록 있는 후보 1명)"
            elif len(away) == 1:
                pid, how = away[0], f"동명이인 정리({season}년 미국 기록 없는 후보 1명, 재확인 권장)"
            else:
                how = f"확인 필요(기록 있는 후보 {len(hit)}명)"
        else:
            how = "확인 필요(영문명 없음)"

        mine = before[before["player_id"] == int(pid)] if pid else before.iloc[0:0]
        last = int(mine["기록시즌"].max()) if len(mine) else None
        savant_name = mine["player_name"].iloc[0] if len(mine) else ""

        p["mlbam_정리"] = pid
        p["번호_정리방법"] = how
        p["savant_이름"] = savant_name
        p["직전기록시즌"] = last if last else ""
        p["직전기록레벨"] = "|".join(sorted(mine[mine["기록시즌"] == last]["레벨"])) if last else ""
        if p["구분"] != "신규":
            p["기록_상태"] = "분석 대상 아님(신규 아님)"
        elif not pid:
            p["기록_상태"] = "번호 없음"
        elif not last:
            p["기록_상태"] = "2023년 이후 기록 없음(확인 필요)"
        elif last < season - 1:
            p["기록_상태"] = f"바로 전 해({season - 1}) 기록 없음, {last} 기록 사용(확인 필요)"
        else:
            p["기록_상태"] = "붙임"
        out_rows.append(p)

        if p["구분"] == "신규" and len(mine):
            m = mine.copy()
            m.insert(0, "KBO시즌", season)
            m.insert(1, "팀", p["팀"])
            m.insert(2, "선수", p["선수(기사 표기)"])
            m.insert(3, "포지션", p["포지션"])
            m.insert(4, "직전시즌여부", m["기록시즌"] == last)
            stat_rows.append(m)

    resolved = pd.DataFrame(out_rows)
    resolved.to_csv("data/kbo_foreign_resolved.csv", index=False, encoding="utf-8-sig")
    stats = pd.concat(stat_rows, ignore_index=True).sort_values(["KBO시즌", "팀", "선수", "기록시즌", "레벨"])
    stats.to_csv("data/kbo_pre_kbo_stats.csv", index=False, encoding="utf-8-sig")

    show = ["시즌", "팀", "선수(기사 표기)", "구분", "mlbam_정리", "savant_이름", "직전기록시즌", "직전기록레벨", "기록_상태"]
    pd.set_option("display.width", 250, "display.max_rows", 100, "display.unicode.east_asian_width", True)
    print(resolved[show].to_string(index=False))
    print("=" * 70)
    new = resolved[resolved["구분"] == "신규"]
    print("신규 선수:", len(new), "명 /", new["기록_상태"].value_counts().to_dict())
    print("기록 줄 수:", len(stats))


if __name__ == "__main__":
    main()
