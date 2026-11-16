"""6단계: 표본을 넓혀 분석용 자료를 만든다. (화면 docs/index.html 이 읽는 docs/data.js 도 여기서 만든다)

실행:  python tools/06_build_dataset.py
입력:  data/kbo_foreign_seasons.csv (05번), data/raw/seasons/*.csv (03번)
결과:  data/analysis_players.csv   2024~2026년 KBO 첫해 외국인 선수: 오기 전 기록 + KBO 첫해 성적
       data/candidates_2026_v1.csv 2026 트리플A 선수(구버전 후보 풀. 지금 후보 풀은 03번이 data/candidates_2026.csv 로 만든다)
       data/raw/people.csv         선수 출생연도 (MLB 공개 Stats API, 한 번 받아 둠)
       docs/data.js                 화면용 자료

대상: MyKBO Stats 목록에서 2024·2025·2026년에 처음 나온 외국인 선수 (시즌 중 교체, 아시아쿼터 포함).
      스탯캐스트(2023~)에 기록이 없는 선수(일본·대만 등에서 온 선수)는 비교에서 빠진다. 빠진 사람도 파일에 남긴다.

이름 연결: MyKBO 영문명과 스탯캐스트 이름이 (악센트·대소문자 무시하고) 같을 때만 연결한다.
      별명 표기(Matthew/Matt 등)는 아래 ALIAS 에 적은 것만 연결하고 "확인 필요"로 표시한다.
      같은 이름이 2명이면 KBO에서 뛴 해에 미국 기록이 없는 쪽을 고른다. 그래도 안 좁혀지면 연결하지 않는다.

오기 전 기록: KBO 첫해 바로 전 해 → 없으면 같은 해(시즌 중 합류로 추정, 확인 필요) → 없으면 그 이전 해.
      한 해에 트리플A·MLB 기록이 다 있으면 공을 더 많이 본(던진) 쪽을 쓴다.

닮음 계산용 표준화: 2023~2026 트리플A 선수(투수 공 500개 이상, 타자 150타석 이상)의 평균·표준편차 기준.
"""
import glob
import json
import os
import re
import time
import unicodedata

import pandas as pd
import requests

RAW = "data/raw/seasons"
FIRST_YEARS = [2024, 2025, 2026]
POOL_YEAR = 2026
P_FEATS = ["velocity", "k_percent", "bb_percent", "swing_miss_percent", "hardhit_percent",
           "xwoba", "launch_angle", "release_extension", "arm_angle"]
B_FEATS = ["launch_speed", "hardhit_percent", "barrels_per_bbe_percent", "xwoba",
           "k_percent", "bb_percent", "swing_miss_percent", "launch_angle"]
FEATS = {"투수": P_FEATS, "타자": B_FEATS}
ROLE_EN = {"투수": "pitcher", "타자": "batter"}
# MyKBO 표기 -> 스탯캐스트 표기. 별명 차이로 보이는 것만. 모두 "확인 필요"로 표시된다.
ALIAS = {
    "William Crowe": "Wil Crowe", "Vincent Velasquez": "Vince Velasquez",
    "Michael Clevinger": "Mike Clevinger", "John Cushing": "Jack Cushing",
    "Matthew Sauer": "Matt Sauer", "Matthew Davidson": "Matt Davidson",
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z ]", " ", s).lower()
    return " ".join(w for w in s.split() if w not in {"jr", "sr", "ii", "iii", "iv"})


def load_raw():
    frames = []
    for path in sorted(glob.glob(os.path.join(RAW, "*.csv"))):
        level, role, year = os.path.basename(path)[:-4].split("_")
        df = pd.read_csv(path, encoding="utf-8-sig")
        df["레벨"], df["role"], df["기록시즌"] = level, role, int(year)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    raw["n"] = raw["player_name"].map(lambda s: norm(" ".join(reversed(str(s).split(", ")))))
    return raw


def load_people(ids):
    """출생연도. MLB 공개 Stats API 에서 번호 100개씩 묶어 받는다. 실패하면 비워 둔다."""
    path = "data/raw/people.csv"
    have = pd.read_csv(path, dtype=str) if os.path.exists(path) else pd.DataFrame(columns=["id", "fullName", "birthDate"])
    need = [i for i in sorted(set(ids)) if str(i) not in set(have["id"])]
    rows = []
    for k in range(0, len(need), 100):
        chunk = ",".join(str(i) for i in need[k:k + 100])
        try:
            r = requests.get("https://statsapi.mlb.com/api/v1/people", params={"personIds": chunk},
                             headers={"User-Agent": "Mozilla/5.0 (research script)"}, timeout=60)
            r.raise_for_status()
            for p in r.json().get("people", []):
                rows.append({"id": str(p["id"]), "fullName": p.get("fullName", ""), "birthDate": p.get("birthDate", "")})
        except Exception as e:
            print("출생연도 받기 실패:", repr(e)[:120])
            break
        time.sleep(2)
    if rows:
        have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
        have.to_csv(path, index=False, encoding="utf-8-sig")
    return have.set_index("id")


def num(x):
    return pd.to_numeric(x, errors="coerce")


def main():
    raw = load_raw()
    kbo = pd.read_csv("data/kbo_foreign_seasons.csv", dtype=str).fillna("")
    kbo["연도"] = kbo["연도"].astype(int)
    kbo_years = kbo.groupby("mykbo_id")["연도"].agg(set).to_dict()
    first = kbo[(kbo["첫해여부"] == "첫해") & (kbo["역할"] == kbo["주역할"]) & kbo["연도"].isin(FIRST_YEARS)]

    # 표준화 기준: 트리플A 전체 연도
    scale = {}
    for role, feats in FEATS.items():
        d = raw[(raw["레벨"] == "AAA") & (raw["role"] == ROLE_EN[role])]
        d = d[d["total_pitches"] >= 500] if role == "투수" else d[d["pa"] >= 150]
        scale[role] = {f: (float(d[f].mean()), float(d[f].std())) for f in feats}

    # ---- 과거 선수 연결
    players = []
    for _, r in first.iterrows():
        role, year = r["역할"], r["연도"]
        mine = raw[raw["role"] == ROLE_EN[role]]
        name = r["영문명"]
        flag = []
        hit = mine[(mine["n"] == norm(name)) & (mine["기록시즌"] <= year)]
        if hit.empty and name in ALIAS:
            hit = mine[(mine["n"] == norm(ALIAS[name])) & (mine["기록시즌"] <= year)]
            if not hit.empty:
                flag.append(f"이름 표기 다름({ALIAS[name]}), 확인 필요")
        ids = sorted(hit["player_id"].unique())
        if len(ids) > 1:
            same = set(mine[(mine["기록시즌"] == year)]["player_id"])
            away = [i for i in ids if i not in same]
            if len(away) == 1:
                flag.append("동명이인 중 KBO 시즌에 미국 기록 없는 쪽, 재확인 권장")
                ids = away
        row = {"KBO첫해": year, "mykbo_id": r["mykbo_id"], "영문명": name, "팀": r["팀"], "역할": role,
               "mlbam": "", "연결": "", "기록시즌": "", "기록레벨": "", "기록_공수": "", "기록_타석": ""}
        if len(ids) != 1:
            row["연결"] = "스탯캐스트 기록 없음(2023~, 미국 밖 리그 가능)" if not ids else "동명이인, 못 정함"
        else:
            pid = ids[0]
            rec = hit[hit["player_id"] == pid]
            row["mlbam"] = int(pid)
            for season, why in [(year - 1, ""), (year, "같은 해 기록(시즌 중 합류 추정), 확인 필요"),
                                (year - 2, f"바로 전 해 기록 없음, {year - 2} 기록"), (year - 3, f"바로 전 해 기록 없음, {year - 3} 기록")]:
                s = rec[rec["기록시즌"] == season]
                if not s.empty:
                    if why:
                        flag.append(why)
                    best = s.sort_values("total_pitches", ascending=False).iloc[0]
                    row.update(기록시즌=season, 기록레벨=best["레벨"], 기록_공수=int(best["total_pitches"]), 기록_타석=int(best["pa"]))
                    for f in FEATS[role]:
                        row[f] = float(best[f])
                    if best["레벨"] == "MLB":
                        flag.append("MLB 기록 기준(상대 수준이 트리플A보다 높음)")
                    if best["total_pitches"] < 300:
                        flag.append("표본 작음(공 300개 미만)")
                    break
            row["연결"] = "연결됨"
        row["주의"] = " / ".join(flag)
        # KBO 첫해 성적
        if role == "투수":
            outs = num(r["투_아웃수"])
            w, l, sv = (r["투_W-L-SV"].split("-") + ["", "", ""])[:3]
            row.update(KBO_이닝=round(outs / 3, 1), KBO_ERA=num(r["투_ERA"]), KBO_WHIP=num(r["투_WHIP"]), KBO_경기=num(r["투_G"]),
                       KBO_선발=num(r["투_GS"]), KBO_승=num(w), KBO_패=num(l), KBO_세이브=num(sv),
                       KBO_삼진=num(r["투_SO"]), KBO_볼넷=num(r["투_BB"]))
        else:
            row.update(KBO_경기=num(r["타_G"]), KBO_타수=num(r["타_AB"]), KBO_타율=num(r["타_AVG"]), KBO_출루율=num(r["타_OBP"]),
                       KBO_장타율=num(r["타_SLG"]), KBO_OPS=num(r["타_OPS"]), KBO_홈런=num(r["타_HR"]),
                       KBO_볼넷=num(r["타_BB"]), KBO_삼진=num(r["타_SO"]))
        yrs = kbo_years[r["mykbo_id"]]
        row["다음해_KBO"] = "" if year == max(kbo["연도"]) else ("있음" if (year + 1) in yrs else "없음")
        players.append(row)
    pl = pd.DataFrame(players)

    # ---- 후보 풀: 2026 트리플A
    # 이미 KBO에 온 적 있는 선수: 번호로 연결된 사람 + MyKBO 2014~2026 외국인 명단과 이름이 같은 사람
    # (이름만 같은 다른 사람이 걸릴 수 있다. "KBO 경력 의심"으로만 쓰고 화면에서 뺄지는 사용자가 고른다)
    kbo_names = set(kbo["영문명"].map(norm)) | {norm(v) for v in ALIAS.values()}
    kbo_ids = {}
    for _, r in pl[pl["mlbam"] != ""].iterrows():
        kbo_ids[int(r["mlbam"])] = r["KBO첫해"]
    pools = {}
    for role in FEATS:
        d = raw[(raw["레벨"] == "AAA") & (raw["role"] == ROLE_EN[role]) & (raw["기록시즌"] == POOL_YEAR)].copy()
        d = d[d["total_pitches"] >= 500] if role == "투수" else d[d["pa"] >= 200]
        # 같은 해 MLB 기록이 있으면 참고로 공 수만 붙인다
        m = raw[(raw["레벨"] == "MLB") & (raw["role"] == ROLE_EN[role]) & (raw["기록시즌"] == POOL_YEAR)].set_index("player_id")["total_pitches"]
        d["MLB_공수"] = d["player_id"].map(m).fillna(0).astype(int)
        d["KBO경력"] = d["player_id"].map(kbo_ids).fillna(0).astype(int)
        by_name = d["n"].isin(kbo_names)
        d.loc[by_name & (d["KBO경력"] == 0), "KBO경력"] = 1  # 1 = 이름이 MyKBO 외국인 명단에 있음
        pools[role] = d

    # ---- 출생연도
    ids = [int(i) for i in pl["mlbam"] if i != ""] + [int(i) for d in pools.values() for i in d["player_id"]]
    people = load_people(ids)

    def birth_year(pid):
        b = people["birthDate"].get(str(pid), "") if len(people) else ""
        return int(b[:4]) if isinstance(b, str) and len(b) >= 4 else None

    pl["출생연도"] = [birth_year(i) if i != "" else None for i in pl["mlbam"]]
    pl["API_이름"] = [people["fullName"].get(str(i), "") if i != "" and len(people) else "" for i in pl["mlbam"]]
    pl.to_csv("data/analysis_players.csv", index=False, encoding="utf-8-sig")

    cand_frames = []
    for role, d in pools.items():
        c = d[["player_id", "player_name", "total_pitches", "pa", "MLB_공수", "KBO경력"] + FEATS[role]].copy()
        c.insert(0, "역할", role)
        c["출생연도"] = [birth_year(i) for i in c["player_id"]]
        cand_frames.append(c)
    cands = pd.concat(cand_frames, ignore_index=True)
    cands.to_csv("data/candidates_2026_v1.csv", index=False, encoding="utf-8-sig")  # 후보 풀은 이제 03번이 만든다(MLB 포함)

    # ---- 화면용 자료
    def clean(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if hasattr(v, "item"):
            v = v.item()
        return round(v, 3) if isinstance(v, float) else v

    out = {"만든날": time.strftime("%Y-%m-%d"), "후보연도": POOL_YEAR, "feats": FEATS, "scale": scale, "past": {}, "cands": {}, "excluded": {}}
    for role, feats in FEATS.items():
        ok = pl[(pl["역할"] == role) & (pl["기록시즌"] != "")]
        out["past"][role] = [{k: clean(v) for k, v in r.items()} for r in ok.to_dict("records")]
        no = pl[(pl["역할"] == role) & (pl["기록시즌"] == "")]
        out["excluded"][role] = [{"KBO첫해": int(r["KBO첫해"]), "영문명": r["영문명"], "팀": r["팀"], "이유": r["연결"]} for r in no.to_dict("records")]
        c = cands[cands["역할"] == role]
        out["cands"][role] = [{k: clean(v) for k, v in r.items() if k in ["player_id", "player_name", "total_pitches", "pa", "MLB_공수", "KBO경력", "출생연도"] + feats}
                              for r in c.to_dict("records")]
    # ---- 선수별 시즌 기록 (상세 그래프용)
    by_player = {k: g for k, g in raw.groupby(["role", "player_id"])}

    def hist_of(role, pid):
        g = by_player.get((ROLE_EN[role], int(pid)))
        if g is None:
            return []
        rows = []
        for _, s in g.sort_values(["기록시즌", "레벨"]).iterrows():
            o = {"y": int(s["기록시즌"]), "lv": s["레벨"], "n": int(s["total_pitches"]), "pa": int(s["pa"])}
            for f in FEATS[role]:
                o[f] = clean(s[f])
            rows.append(o)
        return rows

    def kbo_of(mid, role):
        g = kbo[(kbo["mykbo_id"] == str(mid)) & (kbo["역할"] == role)]
        rows = []
        for y, gg in g.groupby("연도"):
            if role == "투수":
                s = gg.assign(o=num(gg["투_아웃수"])).sort_values("o", ascending=False).iloc[0]
                rows.append({"y": int(y), "팀": s["팀"], "ERA": clean(num(s["투_ERA"])), "WHIP": clean(num(s["투_WHIP"])),
                             "IP": clean(round(float(num(s["투_아웃수"])) / 3, 1)), "SO": clean(num(s["투_SO"])),
                             "BB": clean(num(s["투_BB"])), "G": clean(num(s["투_G"]))})
            else:
                s = gg.assign(o=num(gg["타_AB"])).sort_values("o", ascending=False).iloc[0]
                rows.append({"y": int(y), "팀": s["팀"], "OPS": clean(num(s["타_OPS"])), "AVG": clean(num(s["타_AVG"])),
                             "AB": clean(num(s["타_AB"])), "HR": clean(num(s["타_HR"])), "BB": clean(num(s["타_BB"])),
                             "SO": clean(num(s["타_SO"])), "G": clean(num(s["타_G"]))})
        return rows

    for role in FEATS:
        for rec in out["past"][role]:
            rec["hist"] = hist_of(role, rec["mlbam"])
            rec["kbo"] = kbo_of(rec["mykbo_id"], role)
        for rec in out["cands"][role]:
            rec["hist"] = hist_of(role, rec["player_id"])

    os.makedirs("docs", exist_ok=True)
    # 2026-11-15: 구버전(2024~2026 표본, 스탯캐스트 기준). 화면은 이제 08번이 만드는 docs/data.js 를 읽는다.
    with open("docs/data_v1.js", "w", encoding="utf-8") as f:
        f.write("// tools/06_build_dataset.py(구버전)가 만든 파일. 직접 고치지 않는다.\nwindow.DATA = ")
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    # ---- 보고
    pd.set_option("display.width", 250, "display.max_rows", 200, "display.unicode.east_asian_width", True)
    print(pl.groupby(["역할", "KBO첫해"])["기록시즌"].agg(전체="size", 기록있음=lambda s: (s != "").sum()).to_string())
    print("=" * 70)
    print(pl[pl["주의"] != ""][["KBO첫해", "영문명", "API_이름", "기록시즌", "기록레벨", "주의"]].to_string(index=False))
    print("=" * 70)
    bad = pl[(pl["mlbam"] != "") & (pl["API_이름"].map(norm) != pl["영문명"].map(norm))]
    print("API 이름과 MyKBO 이름이 다른 연결(확인용):")
    print(bad[["영문명", "API_이름", "mlbam"]].to_string(index=False))
    print("=" * 70)
    print("후보 풀:", {r: len(d) for r, d in pools.items()}, "/ 출생연도 없는 후보:", int(cands["출생연도"].isna().sum()))
    print("docs/data.js", os.path.getsize("docs/data.js"), "bytes")


if __name__ == "__main__":
    main()
