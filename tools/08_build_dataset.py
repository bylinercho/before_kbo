"""8단계: "입단 전 5년" 프로필을 만들어 화면용 자료(web/data.js)를 만든다.

실행:  python -I tools/08_build_dataset.py
입력:  data/kbo_cohort.csv, data/raw/history_long.csv (07번), data/kbo_foreign_seasons.csv (05번),
       data/raw/seasons/*.csv (스탯캐스트, 03번), data/candidates_2026.csv (03번이 만든 2026 후보 풀: 트리플A·MLB 합산)
결과:  data/cohort_profiles.csv       지난 사례(2015~2026 KBO 첫해 외국인) 프로필 + KBO 첫해 성적
       data/candidates_profiles.csv   2026 후보 프로필
       web/data.js                    화면용 자료

프로필(비교의 중심)
- 지난 사례: KBO 입단 해 바로 앞 5시즌(입단 해는 제외), 후보: 2022~2026 5시즌.
- 미국 MLB + 트리플A 기록만 합쳐서 비율을 계산한다(타석/상대 타자 150 이상 필요).
  모자라면 더블A 이하를 포함하고 "주의"에 적는다. 그래도 모자라면 비교에서 뺀다.
- 투수: 삼진%, 볼넷%, 홈런%(상대 타자 대비), ERA, 선발 비율 / 타자: 삼진%, 볼넷%, 홈런%(타석 대비), ISO, 타율
- 레벨별 난이도 차이는 보정하지 않았다(MLB와 트리플A를 그냥 합침). MLB 비중을 같이 보여 준다.
- 스탯캐스트 지표는 있는 선수만 보조로 붙인다(MLB 2015~, 트리플A 2023~).
"""
import glob
import json
import os
import re
import sys
import time
import unicodedata

import numpy as np
import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

TRAD = {"투수": ["k_pct", "bb_pct", "hr_pct", "era", "gs_pct"], "타자": ["k_pct", "bb_pct", "hr_pct", "iso", "avg"]}
SC = {"투수": ["velocity", "k_percent", "bb_percent", "swing_miss_percent", "hardhit_percent", "xwoba",
              "launch_angle", "release_extension", "arm_angle"],
      "타자": ["launch_speed", "hardhit_percent", "barrels_per_bbe_percent", "xwoba", "k_percent",
              "bb_percent", "swing_miss_percent", "launch_angle"]}
ROLE_EN = {"투수": "pitcher", "타자": "batter"}
GROUP = {"투수": "pitching", "타자": "hitting"}
VOLCOL = {"투수": "bf", "타자": "pa"}
TOPL = ["MLB", "AAA"]
WINDOW, POOL_YEAR, MIN_VOL = 5, 2026, 150


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z ]", " ", s).lower()
    return " ".join(w for w in s.split() if w not in {"jr", "sr", "ii", "iii", "iv"})


def clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 3)
    return v


def rates(role, d):
    if role == "투수":
        bf, outs = d["bf"].sum(), d["outs"].sum()
        if bf <= 0 or outs <= 0:
            return None
        return {"vol": int(bf), "k_pct": d["so"].sum() / bf * 100, "bb_pct": d["bb"].sum() / bf * 100,
                "hr_pct": d["hr"].sum() / bf * 100, "era": d["er"].sum() * 27 / outs,
                "gs_pct": d["gs"].sum() / max(d["g"].sum(), 1) * 100}
    pa, ab = d["pa"].sum(), d["ab"].sum()
    if pa <= 0 or ab <= 0:
        return None
    h = d["h"].sum()
    tb = h + d["doubles"].sum() + 2 * d["triples"].sum() + 3 * d["hr"].sum()
    return {"vol": int(pa), "k_pct": d["so"].sum() / pa * 100, "bb_pct": d["bb"].sum() / pa * 100,
            "hr_pct": d["hr"].sum() / pa * 100, "iso": (tb - h) / ab, "avg": h / ab}


def profile(role, h, y0, y1):
    """h: 선수 한 명의 기록. 반환: (프로필 dict 또는 None, 주의 문구, 사유)"""
    w = h[(h["season"] >= y0) & (h["season"] <= y1)]
    top = w[w["level"].isin(TOPL)]
    note, r = "", rates(role, top)
    if r is None or r["vol"] < MIN_VOL:
        r2 = rates(role, w)
        if r2 and r2["vol"] >= MIN_VOL:
            r, note = r2, "MLB·AAA 기록이 150 미만이라 AA 이하 기록을 포함"
            top = w
        else:
            return None, "", "5년 합계 표본 부족(MLB·AAA 기준)"
    v = VOLCOL[role]
    r["mlb_share"] = float(top[top["level"] == "MLB"][v].sum() / max(top[v].sum(), 1))
    r["years"] = f"{int(w['season'].min())}~{int(w['season'].max())}"
    if y1 not in set(w["season"]):
        gap = f"{y1}년 미국 기록 없음(일본 등 다른 리그에서 뛰었을 수 있음)"
        note = f"{note} / {gap}" if note else gap
    return r, note, ""


def hist_rows(role, h, y0, y1):
    w = h[(h["season"] >= y0) & (h["season"] <= y1)]
    out = []
    for (season, level), d in w.groupby(["season", "level"]):
        r = rates(role, d)
        if r:
            out.append({"y": int(season), "lv": level, **{k: clean(v) for k, v in r.items()}})
    return out


def load_people(ids):
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
            rows += [{"id": str(p["id"]), "fullName": p.get("fullName", ""), "birthDate": p.get("birthDate", "")} for p in r.json().get("people", [])]
        except Exception as e:
            print("출생연도 받기 실패:", repr(e)[:120])
            break
        time.sleep(2)
    if rows:
        have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("id")
        have.to_csv(path, index=False, encoding="utf-8-sig")
    return have.set_index("id")


def load_savant():
    frames = []
    for path in sorted(glob.glob("data/raw/seasons/*.csv")):
        level, role, year = os.path.basename(path)[:-4].split("_")
        df = pd.read_csv(path, encoding="utf-8-sig")
        df["레벨"], df["role"], df["기록시즌"] = level, role, int(year)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def num(x):
    return pd.to_numeric(x, errors="coerce")


def main():
    co = pd.read_csv("data/kbo_cohort.csv", dtype=str).fillna("")
    kn = {}  # mykbo_id -> 한국 등록명 (09번이 MyKBO 선수 페이지에서 받음. 없으면 빈 칸)
    if os.path.exists("data/kbo_korean_names.csv"):
        k = pd.read_csv("data/kbo_korean_names.csv", dtype=str).fillna("")
        kn = dict(zip(k["mykbo_id"], k["한국등록명"]))
    co["KBO첫해"] = co["KBO첫해"].astype(int)
    hist = pd.read_csv("data/raw/history_long.csv", encoding="utf-8-sig")
    hist_by = {k: g for k, g in hist.groupby(["id", "group"])}
    kbo = pd.read_csv("data/kbo_foreign_seasons.csv", dtype=str).fillna("")
    kbo["연도"] = kbo["연도"].astype(int)
    kbo_names = set(kbo["영문명"].map(norm)) | set(pd.read_csv("data/kbo_foreign_pre2014.csv", dtype=str)["영문명"].map(norm))
    pool = pd.read_csv("data/candidates_2026.csv")
    sav = load_savant()

    def get_h(pid, role):
        return hist_by.get((int(pid), GROUP[role]))

    # ---------- 지난 사례
    past, excluded = [], []
    for _, r in co.iterrows():
        role, debut = r["역할"], r["KBO첫해"]
        if r["연결"] != "연결됨":
            excluded.append({"KBO첫해": debut, "영문명": r["영문명"], "한글명": kn.get(r["mykbo_id"], ""), "팀": r["팀"], "역할": role,
                             "이유": r["연결"] if r["연결"] else "연결 안 됨"})
            continue
        h = get_h(r["mlbam"], role)
        prof, note, why = profile(role, h, debut - WINDOW, debut - 1)
        if prof is None:
            excluded.append({"KBO첫해": debut, "영문명": r["영문명"], "한글명": kn.get(r["mykbo_id"], ""), "팀": r["팀"], "역할": role, "이유": why})
            continue
        rec = {"KBO첫해": debut, "mykbo_id": r["mykbo_id"], "영문명": r["영문명"], "한글명": kn.get(r["mykbo_id"], ""), "팀": r["팀"], "역할": role,
               "mlbam": int(r["mlbam"]), "창": prof.pop("years"), **{k: clean(v) for k, v in prof.items()}}
        flags = [note] if note else []
        if "확인 필요" in r["연결방법"]:
            flags.append("이름 연결: " + r["연결방법"])
        if rec["mlb_share"] < 0.2:
            flags.append("MLB 비중이 낮음(트리플A 위주)")
        rec["주의"] = " / ".join(flags)
        rec["hist"] = hist_rows(role, h, debut - WINDOW, debut - 1)
        # KBO 첫해 성적과 이후 기록
        k = kbo[(kbo["mykbo_id"] == r["mykbo_id"]) & (kbo["역할"] == role)]
        yrs = set(k["연도"])
        fy = k[k["연도"] == debut]
        if role == "투수":
            s = fy.assign(o=num(fy["투_아웃수"])).sort_values("o", ascending=False).iloc[0]
            w, l, sv = (s["투_W-L-SV"].split("-") + ["", "", ""])[:3]
            rec.update(KBO_이닝=clean(round(float(num(s["투_아웃수"])) / 3, 1)), KBO_ERA=clean(num(s["투_ERA"])), KBO_WHIP=clean(num(s["투_WHIP"])),
                       KBO_경기=clean(num(s["투_G"])), KBO_선발=clean(num(s["투_GS"])), KBO_승=clean(num(w)), KBO_패=clean(num(l)),
                       KBO_삼진=clean(num(s["투_SO"])), KBO_볼넷=clean(num(s["투_BB"])))
        else:
            s = fy.assign(o=num(fy["타_AB"])).sort_values("o", ascending=False).iloc[0]
            rec.update(KBO_경기=clean(num(s["타_G"])), KBO_타수=clean(num(s["타_AB"])), KBO_타율=clean(num(s["타_AVG"])),
                       KBO_출루율=clean(num(s["타_OBP"])), KBO_장타율=clean(num(s["타_SLG"])), KBO_OPS=clean(num(s["타_OPS"])),
                       KBO_홈런=clean(num(s["타_HR"])), KBO_볼넷=clean(num(s["타_BB"])), KBO_삼진=clean(num(s["타_SO"])))
        rec["다음해_KBO"] = "" if debut >= POOL_YEAR else ("있음" if (debut + 1) in yrs else "없음")
        rows = []
        for y, gg in k.groupby("연도"):
            if role == "투수":
                s = gg.assign(o=num(gg["투_아웃수"])).sort_values("o", ascending=False).iloc[0]
                rows.append({"y": int(y), "팀": s["팀"], "ERA": clean(num(s["투_ERA"])), "WHIP": clean(num(s["투_WHIP"])),
                             "IP": clean(round(float(num(s["투_아웃수"])) / 3, 1)), "SO": clean(num(s["투_SO"])), "BB": clean(num(s["투_BB"])), "G": clean(num(s["투_G"]))})
            else:
                s = gg.assign(o=num(gg["타_AB"])).sort_values("o", ascending=False).iloc[0]
                rows.append({"y": int(y), "팀": s["팀"], "OPS": clean(num(s["타_OPS"])), "AVG": clean(num(s["타_AVG"])), "AB": clean(num(s["타_AB"])),
                             "HR": clean(num(s["타_HR"])), "BB": clean(num(s["타_BB"])), "SO": clean(num(s["타_SO"])), "G": clean(num(s["타_G"]))})
        rec["kbo"] = rows
        # 스탯캐스트 보조: 5년 창 안에서 가장 최근 기록
        sv = sav[(sav["role"] == ROLE_EN[role]) & (sav["player_id"] == int(r["mlbam"])) & (sav["기록시즌"] >= debut - WINDOW) & (sav["기록시즌"] <= debut - 1)]
        if len(sv):
            best = sv.sort_values(["기록시즌", "total_pitches"], ascending=[False, False]).iloc[0]
            sc = {f: clean(best[f]) for f in SC[role]}
            if all(v is not None for v in sc.values()):
                rec["sc"] = {"y": int(best["기록시즌"]), "lv": best["레벨"], "n": int(best["total_pitches"]), **sc}
        past.append(rec)

    # ---------- 2026 후보
    cand_ids = {int(r["mlbam"]) for r in past}
    mlb_ko = {int(r["mlbam"]): r["한글명"] for r in past if r["한글명"]}  # 2026 후보 중 KBO에 왔던 선수는 한국 등록명도 붙인다
    cands, dropped = [], 0
    for _, c in pool.iterrows():
        role = c["역할"]
        h = get_h(c["player_id"], role)
        if h is None:
            dropped += 1
            continue
        prof, note, why = profile(role, h, POOL_YEAR - WINDOW + 1, POOL_YEAR)
        if prof is None:
            dropped += 1
            continue
        name_flag = norm(" ".join(reversed(str(c["player_name"]).split(", ")))) in kbo_names
        rec = {"player_id": int(c["player_id"]), "player_name": c["player_name"], "한글명": mlb_ko.get(int(c["player_id"]), ""),
               "역할": role, "창": prof.pop("years"),
               **{k: clean(v) for k, v in prof.items()}, "total_pitches": int(c["total_pitches"]), "pa26": int(c["pa"]),
               "MLB_공수": int(c["MLB_공수"]), "소속": c["소속"],
               "KBO경력": 1 if (name_flag or int(c["player_id"]) in cand_ids) else 0, "주의": note}
        rec["hist"] = hist_rows(role, h, POOL_YEAR - WINDOW + 1, POOL_YEAR)
        sc = {f: clean(c[f]) for f in SC[role]}
        if all(v is not None for v in sc.values()):
            rec["sc"] = {"y": POOL_YEAR, "lv": c["sc_level"], "n": int(c["sc_n"]), **sc}
        cands.append(rec)

    # ---------- 출생연도
    people = load_people([r["mlbam"] for r in past] + [c["player_id"] for c in cands])

    def by(pid):
        b = people["birthDate"].get(str(pid), "") if len(people) else ""
        return int(b[:4]) if isinstance(b, str) and len(b) >= 4 else None

    for r in past:
        r["출생연도"] = by(r["mlbam"])
    for c in cands:
        c["출생연도"] = by(c["player_id"])

    # ---------- 표준화 기준: 지난 사례 + 후보 전체
    scale = {}
    for role, feats in TRAD.items():
        allp = [r for r in past + cands if r["역할"] == role]
        scale[role] = {f: [float(np.mean([r[f] for r in allp])), float(np.std([r[f] for r in allp], ddof=1))] for f in feats}
    sdf = sav[(sav["레벨"] == "AAA")]
    sscale = {}
    for role, feats in SC.items():
        d = sdf[sdf["role"] == ROLE_EN[role]]
        d = d[d["total_pitches"] >= 500] if role == "투수" else d[d["pa"] >= 150]
        sscale[role] = {f: [float(d[f].mean()), float(d[f].std())] for f in feats}

    out = {"만든날": time.strftime("%Y-%m-%d"), "후보연도": POOL_YEAR, "창길이": WINDOW, "feats": TRAD, "scale": scale,
           "sfeats": SC, "sscale": sscale, "past": {}, "cands": {}, "excluded": {}}
    for role in TRAD:
        out["past"][role] = [r for r in past if r["역할"] == role]
        out["cands"][role] = [c for c in cands if c["역할"] == role]
        out["excluded"][role] = [e for e in excluded if e["역할"] == role]
    os.makedirs("web", exist_ok=True)
    with open("web/data.js", "w", encoding="utf-8") as f:
        f.write("// tools/08_build_dataset.py 가 만든 파일. 직접 고치지 않는다.\nwindow.DATA = ")
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    pd.DataFrame([{k: v for k, v in r.items() if k not in ("hist", "kbo", "sc")} for r in past]).to_csv("data/cohort_profiles.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{k: v for k, v in c.items() if k not in ("hist", "sc")} for c in cands]).to_csv("data/candidates_profiles.csv", index=False, encoding="utf-8-sig")

    # ---------- 보고
    pd.set_option("display.width", 250, "display.max_rows", 200, "display.unicode.east_asian_width", True)
    tot = co.groupby(["KBO첫해", "역할"]).size().unstack(fill_value=0)
    used = pd.DataFrame(past).groupby(["KBO첫해", "역할"]).size().unstack(fill_value=0)
    rep = tot.add_suffix("_전체").join(used.add_suffix("_비교가능"), how="left").fillna(0).astype(int)
    print(rep.to_string())
    print("합계: 전체", len(co), "→ 비교 가능", len(past), "(투수", len(out["past"]["투수"]), "/ 타자", len(out["past"]["타자"]), ")")
    print("제외 사유:", pd.DataFrame(excluded)["이유"].value_counts().to_dict())
    print("후보:", {r: len(v) for r, v in out["cands"].items()}, "탈락(5년 기록 부족 등):", dropped)
    print("스탯캐스트 보조 있음: 지난 사례", sum("sc" in r for r in past), "/", len(past), ", 후보", sum("sc" in c for c in cands), "/", len(cands))
    print("web/data.js", os.path.getsize("web/data.js"), "bytes")
    print({r: {f: [round(a, 2) for a in v] for f, v in s.items()} for r, s in scale.items()})


if __name__ == "__main__":
    main()
