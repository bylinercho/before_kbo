"""7단계: KBO 첫해 외국인 선수(2015~2026 입단)의 "입단 전 5년" 미국 기록을 받는다.

실행:  python -I tools/07_fetch_history.py
입력:  data/kbo_foreign_seasons.csv (05번), data/kbo_foreign_pre2014.csv (05번), data/candidates_2026.csv (03번, 후보 풀)
       체드윅 선수 명부(없으면 02번 도구가 data/raw/chadwick/ 에 받는다. 약 65MB)
결과:  data/raw/history_long.csv   선수·시즌·레벨별 기록 (MLB 공식 Stats API, 전통 기록)
       data/kbo_cohort.csv         첫해 선수 명단 + 선수 번호 연결 결과

왜 이 방식인가 (2026-11-15 확인)
- 스탯캐스트는 MLB가 2015년부터, 트리플A는 2023년부터만 있다. 2015~2022년 입단자의 마이너 기록은 스탯캐스트로는 없다.
- MLB 공식 Stats API는 MLB·트리플A·더블A·하이A·A 레벨의 시즌별 전통 기록(타석, 삼진, 볼넷, 홈런, 이닝 등)을 준다.
  그래서 "입단 전 5년" 비교는 이 전통 기록으로 한다. 스탯캐스트는 있는 선수만 보조로 쓴다(08번).

대상: MyKBO 목록에 2015~2026년에 처음 나온 외국인(주 역할 기준). MyKBO 목록이 2014년부터만 완전해서
      2014년 목록에 처음 나온 선수는 첫해를 알 수 없어 뺐다. 2010~2013년 부분 명단에 이름이 있는 사람도
      이전 KBO 경력자로 보고 뺐다(이름이 같은 다른 사람일 수 있다).

이름 연결: ① 체드윅 명부에서 이름(악센트·대소문자 무시)이 같은 사람 ② 별명 표(ALIAS) ③ 성이 같고 이름 앞 3글자가 같은 사람(확인 필요)
      후보가 여럿이면 "입단 전 5년 동안 미국 기록이 있는 후보가 딱 한 명"일 때만 고른다. 아니면 비워 둔다.
      Asian Quota 등 미국 기록이 없는 선수는 연결되지 않는다.
수동 지정: data/manual_links.csv (영문명, KBO첫해, mlbam)에 적은 선수는 위 규칙을 건너뛰고 그 번호로 연결한다(운영자가 확인한 선수).

규칙: 요청은 100명씩 묶어 보내고 사이에 쉰다. 이미 받은 (레벨, 선수)는 다시 받지 않는다.
"""
import importlib.util
import os
import sys
import time

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

LEVELS = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A"}
HIST = "data/raw/history_long.csv"
FETCHED = "data/raw/history_fetched.txt"
ALIAS = {
    "William Crowe": "Wil Crowe", "Vincent Velasquez": "Vince Velasquez", "Michael Clevinger": "Mike Clevinger",
    "John Cushing": "Jack Cushing", "Matthew Sauer": "Matt Sauer", "Matthew Davidson": "Matt Davidson",
}
COLS = ["id", "season", "level", "group", "g", "gs", "outs", "bf", "so", "bb", "hr", "er", "h",
        "pa", "ab", "doubles", "triples", "sb", "hbp", "sf", "tb"]


def load_m02():
    spec = importlib.util.spec_from_file_location("m02", "tools/02_match_ids.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def outs_of(ip):
    """'62.2' (= 62과 3분의 2이닝) -> 아웃 수 188"""
    whole, _, frac = str(ip).partition(".")
    return int(whole) * 3 + (int(frac) if frac else 0)


def parse_person(p, sport):
    rows = []
    for blk in p.get("stats", []):
        group = blk["group"]["displayName"]
        by = {}
        for s in blk.get("splits", []):
            # MLB 시스템은 멕시칸 리그를 트리플A로 분류한다. 미국 트리플A와 수준이 달라 "MEX"로 따로 둔다.
            # '2018.1' 처럼 전·후반기로 나뉜 시즌 값은 정수 연도로 합친다.
            level = "MEX" if (sport == 11 and s.get("league", {}).get("name") == "Mexican League") else LEVELS[sport]
            by.setdefault((int(float(s["season"])), level), []).append(s)
        for (season, level), splits in by.items():
            # 두 팀 이상이면 합계 줄(team 없음)이 따로 있으니, 팀별 줄만 더한다. 팀 줄이 없을 때만 합계 줄을 쓴다.
            teamed = [s for s in splits if "team" in s]
            use = teamed if teamed else splits
            agg = {c: 0 for c in COLS[4:]}
            for s in use:
                st = s["stat"]
                if group == "pitching":
                    agg["g"] += st.get("gamesPlayed", 0); agg["gs"] += st.get("gamesStarted", 0)
                    agg["outs"] += outs_of(st.get("inningsPitched", "0.0")); agg["bf"] += st.get("battersFaced", 0)
                    agg["so"] += st.get("strikeOuts", 0); agg["bb"] += st.get("baseOnBalls", 0)
                    agg["hr"] += st.get("homeRuns", 0); agg["er"] += st.get("earnedRuns", 0); agg["h"] += st.get("hits", 0)
                    agg["hbp"] += st.get("hitBatsmen", 0)
                else:
                    agg["g"] += st.get("gamesPlayed", 0); agg["pa"] += st.get("plateAppearances", 0)
                    agg["ab"] += st.get("atBats", 0); agg["h"] += st.get("hits", 0)
                    agg["doubles"] += st.get("doubles", 0); agg["triples"] += st.get("triples", 0)
                    agg["hr"] += st.get("homeRuns", 0); agg["bb"] += st.get("baseOnBalls", 0)
                    agg["so"] += st.get("strikeOuts", 0); agg["sb"] += st.get("stolenBases", 0)
                    agg["hbp"] += st.get("hitByPitch", 0); agg["sf"] += st.get("sacFlies", 0)
                    agg["tb"] += st.get("totalBases", 0)
            if agg["bf"] + agg["pa"] > 0:
                rows.append({"id": p["id"], "season": season, "level": level, "group": group, **agg})
    return rows


def fetch_history(ids):
    done = set(open(FETCHED, encoding="utf-8").read().split()) if os.path.exists(FETCHED) else set()
    new_total = 0
    for sport in LEVELS:
        todo = [i for i in sorted(ids) if f"{sport}:{i}" not in done]
        for k in range(0, len(todo), 100):
            chunk = todo[k:k + 100]
            r = requests.get("https://statsapi.mlb.com/api/v1/people", timeout=120,
                             headers={"User-Agent": "Mozilla/5.0 (research script)"},
                             params={"personIds": ",".join(map(str, chunk)),
                                     "hydrate": f"stats(group=[pitching,hitting],type=[yearByYear],sportId={sport})"})
            r.raise_for_status()
            rows = []
            for p in r.json().get("people", []):
                rows += parse_person(p, sport)
            if rows:
                pd.DataFrame(rows, columns=COLS).to_csv(HIST, mode="a", index=False, header=not os.path.exists(HIST), encoding="utf-8-sig")
            with open(FETCHED, "a", encoding="utf-8") as f:
                f.write("".join(f"{sport}:{i}\n" for i in chunk))
            new_total += len(rows)
            print(f"{LEVELS[sport]} {k + len(chunk)}/{len(todo)}명 처리, 새 기록 {len(rows)}줄", flush=True)
            time.sleep(2)
    return new_total


def main():
    os.makedirs("data/raw", exist_ok=True)
    m02 = load_m02()
    norm = m02.norm
    reg = m02.load_register()
    reg["first_year"] = pd.to_numeric(reg["pro_played_first"], errors="coerce")
    reg["ln"] = reg["name_last"].fillna("").map(norm)
    reg["fn"] = reg["name_first"].fillna("").map(norm)

    kbo = pd.read_csv("data/kbo_foreign_seasons.csv", dtype=str).fillna("")
    kbo["연도"] = kbo["연도"].astype(int)
    pre_names = set(pd.read_csv("data/kbo_foreign_pre2014.csv", dtype=str)["영문명"].map(norm))
    first = kbo[(kbo["첫해여부"] == "첫해") & (kbo["역할"] == kbo["주역할"]) & (kbo["연도"] >= 2015)].copy()
    first["이전KBO경력의심"] = first["영문명"].map(norm).isin(pre_names)
    print("첫해 선수:", len(first), "명 / 2010~2013 명단에 이름이 있어 제외:", int(first["이전KBO경력의심"].sum()), "명")
    first = first[~first["이전KBO경력의심"]].drop_duplicates(["mykbo_id"])

    # 이름 후보
    cohort = []
    for _, r in first.iterrows():
        name, debut = r["영문명"], r["연도"]
        n = norm(name)
        cand, how = reg[reg["full"] == n], "이름 일치"
        if cand.empty and name in ALIAS:
            cand, how = reg[reg["full"] == norm(ALIAS[name])], f"별명 표기({ALIAS[name]}), 확인 필요"
        if cand.empty:
            parts = n.split()
            if len(parts) >= 2:
                cand = reg[(reg["ln"] == parts[-1]) & (reg["fn"].str[:3] == parts[0][:3])]
                how = "이름 비슷(성 같고 이름 앞 3글자 같음), 확인 필요"
        cand = cand[cand["first_year"].isna() | (cand["first_year"] <= debut - 1)]
        cohort.append({"KBO첫해": debut, "mykbo_id": r["mykbo_id"], "영문명": name, "팀": r["팀"], "역할": r["역할"],
                       "후보번호": "|".join(cand["key_mlbam"].astype(str)), "연결방법": how if len(cand) else "체드윅에 없음"})
    co = pd.DataFrame(cohort)
    if os.path.exists("data/manual_links.csv"):
        man = pd.read_csv("data/manual_links.csv", dtype=str, encoding="utf-8-sig").fillna("")
        done = 0
        for _, m in man.iterrows():
            hit = co[(co["영문명"].map(norm) == norm(m["영문명"])) & (co["KBO첫해"] == int(m["KBO첫해"]))]
            if hit.empty:
                print("수동 지정 대상을 못 찾음:", m["영문명"], m["KBO첫해"])
                continue
            co.loc[hit.index, "후보번호"] = m["mlbam"]
            co.loc[hit.index, "연결방법"] = "수동 지정(운영자 확인)"
            done += 1
        print("수동 지정 반영:", done, "/", len(man), "명")

    ids = {int(i) for s in co["후보번호"] for i in s.split("|") if i}
    pool = pd.read_csv("data/candidates_2026.csv")
    ids |= {int(i) for i in pool["player_id"]}
    print("받을 선수 번호:", len(ids), "명 (과거 후보", len({int(i) for s in co["후보번호"] for i in s.split("|") if i}), "+ 2026 후보 풀)")
    fetch_history(ids)

    # 후보 가운데 "입단 전 5년 동안 기록이 있는" 사람 고르기
    h = pd.read_csv(HIST, encoding="utf-8-sig")
    chosen, status = [], []
    for _, r in co.iterrows():
        group = "pitching" if r["역할"] == "투수" else "hitting"
        vol_col = "bf" if group == "pitching" else "pa"
        if str(r["연결방법"]).startswith("수동 지정"):
            chosen.append(int(r["후보번호"])); status.append("연결됨")
            continue
        ok = []
        for i in [int(x) for x in r["후보번호"].split("|") if x]:
            d = h[(h["id"] == i) & (h["group"] == group) & (h["season"] >= r["KBO첫해"] - 5) & (h["season"] <= r["KBO첫해"] - 1)]
            if d[vol_col].sum() > 0:
                ok.append(i)
        if len(ok) > 1:  # 동명이인: 입단 해에 미국 기록이 없는 쪽(KBO로 간 사람)만 남는지 본다
            away = [i for i in ok if not ((h["id"] == i) & (h["group"] == group) & (h["season"] == r["KBO첫해"])).any()]
            if len(away) == 1:
                ok = away
                co.loc[_, "연결방법"] += "; 동명이인 중 입단 해 미국 기록 없는 쪽, 확인 필요"
        if len(ok) == 1:
            chosen.append(ok[0]); status.append("연결됨")
        else:
            chosen.append(""); status.append("체드윅에 없음" if not r["후보번호"] else ("입단 전 5년 미국 기록 없음" if not ok else "동명이인, 못 정함"))
    co["mlbam"], co["연결"] = chosen, status
    co.to_csv("data/kbo_cohort.csv", index=False, encoding="utf-8-sig")
    print("=" * 70)
    print(co.groupby(["KBO첫해", "연결"]).size().unstack(fill_value=0).to_string())
    print("연결됨 합계:", int((co["연결"] == "연결됨").sum()), "/", len(co))
    print(co["연결방법"].value_counts().to_string())


if __name__ == "__main__":
    main()
