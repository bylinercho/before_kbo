"""8단계: "입단 전 5년" 프로필을 만들어 화면용 자료(docs/data.js)를 만든다.

실행:  python -I tools/08_build_dataset.py
입력:  data/kbo_cohort.csv, data/raw/history_long.csv (07번), data/kbo_foreign_seasons.csv (05번),
       data/raw/seasons/*.csv (스탯캐스트, 03번), data/candidates_2026.csv (03번이 만든 2026 후보 풀: 트리플A·MLB 합산)
결과:  data/cohort_profiles.csv       지난 사례(2015~2026 KBO 첫해 외국인) 프로필 + KBO 첫해 성적
       data/candidates_profiles.csv   2026 후보 프로필
       docs/data.js                    화면용 자료

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
from scipy.stats import mannwhitneyu
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, silhouette_score
from sklearn.model_selection import RepeatedStratifiedKFold

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


LG = {}  # (시즌, 레벨) -> 리그 평균 비율 (10번이 만든 data/league_rates.csv)
IL = {}  # 선수 번호 -> 부상자 명단 등재 기록 (13번이 만든 data/il_stints.csv)
ARS = None  # 구종 사용 비율 (12번이 만든 data/pitch_arsenal.csv, MLB 투수만)


def il_summary(pid, y0, y1):
    """y0~y1년에 시작된 부상자 명단 등재를 요약. 기록이 없으면 0건(부상이 없었거나 API에 기록이 없는 것 — 구분할 수 없다)."""
    g = IL.get(int(pid))
    empty = {"n": 0, "days": 0, "max": 0, "tj": 0, "by": {}, "stints": []}
    if g is None:
        return empty
    w = g[(g["start"] >= f"{y0}-01-01") & (g["start"] <= f"{y1}-12-31")].sort_values("start", ascending=False)
    if w.empty:
        return empty
    txt = w["text"].fillna("")
    by = w.groupby(w["start"].str[:4])["days"].sum()
    return {"n": int(len(w)), "days": int(w["days"].sum()), "max": int(w["days"].max()),
            "tj": int(txt.str.contains("tommy john", case=False).any()), "by": {k: int(v) for k, v in by.items()},
            "stints": [{"s": r["start"], "e": r["end"], "d": int(r["days"]), "k": int(r["kind"]), "t": str(r["text"])[:90] if isinstance(r["text"], str) else "", "o": int(r["open"])}
                       for _, r in w.head(12).iterrows()]}


def arsenal_of(pid, y0, y1):
    """y0~y1년 중 가장 최근 MLB 시즌의 구종 사용 비율(%). 없으면 None."""
    if ARS is None:
        return None
    a = ARS[(ARS["player_id"] == int(pid)) & (ARS["year"] >= y0) & (ARS["year"] <= y1)].sort_values("year")
    if a.empty:
        return None
    r = a.iloc[-1]
    use = {c[2:]: round(float(r[c]), 1) for c in ARS.columns if c.startswith("n_") and pd.notna(r[c]) and r[c] > 0}
    return {"y": int(r["year"]), "use": use} if use else None


def adj_rates(role, d):
    """환경 보정 지수: 같은 해·같은 레벨 리그 평균 대비 (관측 합계 ÷ 리그 평균으로 기대한 합계 × 100). 100 = 리그 평균.
    투수: 삼진%, 볼넷%, 홈런%, ERA(낮을수록 좋음). 타자: 삼진%, 볼넷%, 홈런%, ISO, 타율. 선발 비율은 보정하지 않는다.
    리그 평균이 없는 레벨(멕시칸 리그 등)의 행은 분자·분모에서 함께 뺀다."""
    out = {}
    if role == "투수":
        o = dict(k=0.0, bb=0.0, hr=0.0, er=0.0)
        e = dict(k=0.0, bb=0.0, hr=0.0, er=0.0)
        for _, s in d.iterrows():
            L = LG.get((int(s["season"]), s["level"]))
            if L is None:
                continue
            o["k"] += s["so"]; e["k"] += s["bf"] * L["p_k"] / 100
            o["bb"] += s["bb"]; e["bb"] += s["bf"] * L["p_bb"] / 100
            o["hr"] += s["hr"]; e["hr"] += s["bf"] * L["p_hr"] / 100
            o["er"] += s["er"]; e["er"] += s["outs"] * L["p_era"] / 27
        for key, name in (("k", "k_pct"), ("bb", "bb_pct"), ("hr", "hr_pct"), ("er", "era")):
            out[name] = o[key] / e[key] * 100 if e[key] > 0 else None
        out["gs_pct"] = d["gs"].sum() / max(d["g"].sum(), 1) * 100
    else:
        o = dict(k=0.0, bb=0.0, hr=0.0, xb=0.0, h=0.0)
        e = dict(k=0.0, bb=0.0, hr=0.0, xb=0.0, h=0.0)
        for _, s in d.iterrows():
            L = LG.get((int(s["season"]), s["level"]))
            if L is None:
                continue
            tb = s["h"] + s["doubles"] + 2 * s["triples"] + 3 * s["hr"]
            o["k"] += s["so"]; e["k"] += s["pa"] * L["h_k"] / 100
            o["bb"] += s["bb"]; e["bb"] += s["pa"] * L["h_bb"] / 100
            o["hr"] += s["hr"]; e["hr"] += s["pa"] * L["h_hr"] / 100
            o["xb"] += tb - s["h"]; e["xb"] += s["ab"] * L["h_iso"]
            o["h"] += s["h"]; e["h"] += s["ab"] * L["h_avg"]
        for key, name in (("k", "k_pct"), ("bb", "bb_pct"), ("hr", "hr_pct"), ("xb", "iso"), ("h", "avg")):
            out[name] = o[key] / e[key] * 100 if e[key] > 0 else None
    return out


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
    r["adj"] = adj_rates(role, top)
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
            a = adj_rates(role, d) if (int(season), level) in LG else None
            out.append({"y": int(season), "lv": level, **{k: clean(v) for k, v in r.items()},
                        "adj": {k: clean(v) for k, v in a.items()} if a else None})
    return out


PEOPLE_COLS = ["id", "fullName", "birthDate", "bat", "throw", "country", "pos", "height", "weight"]


def load_people(ids):
    """MLB 선수 정보(생년월일·타격손·투구손·출생국·포지션·키·몸무게). 새 열이 없던 옛 캐시는 비어 있는 선수만 다시 받는다."""
    path = "data/raw/people.csv"
    have = pd.read_csv(path, dtype=str).fillna("") if os.path.exists(path) else pd.DataFrame(columns=PEOPLE_COLS)
    for c in PEOPLE_COLS:
        if c not in have.columns:
            have[c] = ""
    done = set(have.loc[have["pos"] != "", "id"])
    need = [i for i in sorted(set(ids)) if str(i) not in done]
    rows = []
    for k in range(0, len(need), 100):
        chunk = ",".join(str(i) for i in need[k:k + 100])
        try:
            r = requests.get("https://statsapi.mlb.com/api/v1/people", params={"personIds": chunk},
                             headers={"User-Agent": "Mozilla/5.0 (research script)"}, timeout=60)
            r.raise_for_status()
            for p in r.json().get("people", []):
                rows.append({"id": str(p["id"]), "fullName": p.get("fullName", ""), "birthDate": p.get("birthDate", ""),
                             "bat": (p.get("batSide") or {}).get("code", ""), "throw": (p.get("pitchHand") or {}).get("code", ""),
                             "country": p.get("birthCountry", ""), "pos": (p.get("primaryPosition") or {}).get("abbreviation", ""),
                             "height": p.get("height", ""), "weight": str(p.get("weight", "") or "")})
        except Exception as e:
            print("선수 정보 받기 실패:", repr(e)[:120])
            break
        time.sleep(2)
    if rows:
        have = pd.concat([have[~have["id"].isin([r["id"] for r in rows])], pd.DataFrame(rows)], ignore_index=True)
        have[PEOPLE_COLS].to_csv(path, index=False, encoding="utf-8-sig")
    return have.set_index("id")


COUNTRY_KO = {"USA": "미국", "Dominican Republic": "도미니카공화국", "Venezuela": "베네수엘라", "Cuba": "쿠바", "Mexico": "멕시코",
              "Puerto Rico": "푸에르토리코", "Canada": "캐나다", "Japan": "일본", "South Korea": "한국", "Colombia": "콜롬비아",
              "Panama": "파나마", "Australia": "호주", "Taiwan": "대만", "Curacao": "퀴라소", "Curaçao": "퀴라소", "Netherlands": "네덜란드",
              "Nicaragua": "니카라과", "Brazil": "브라질", "Aruba": "아루바", "Bahamas": "바하마", "Honduras": "온두라스",
              "Peru": "페루", "Germany": "독일", "Italy": "이탈리아", "Great Britain": "영국", "United Kingdom": "영국", "Jamaica": "자메이카",
              "Virgin Islands": "버진아일랜드", "Republic of Korea": "한국", "Portugal": "포르투갈", "Slovakia": "슬로바키아", "Czech Republic": "체코", "Lithuania": "리투아니아", "South Africa": "남아공", "China": "중국"}
POS_KO = {"P": "투수", "C": "포수", "1B": "1루수", "2B": "2루수", "3B": "3루수", "SS": "유격수", "LF": "좌익수", "CF": "중견수",
          "RF": "우익수", "OF": "외야수", "IF": "내야수", "DH": "지명타자", "TWP": "투타겸업"}


def bio_of(people, pid):
    """화면에 쓸 선수 신상: 포지션, 투구손(R/L), 타격손(R/L/S), 출생국(한글), 키(cm), 몸무게(kg). 값이 없으면 키를 뺀다."""
    if not len(people) or str(pid) not in people.index:
        return None
    r = people.loc[str(pid)]
    out = {}
    if r["pos"]:
        out["pos"] = r["pos"]
    if r["throw"]:
        out["thr"] = r["throw"]
    if r["bat"]:
        out["bat"] = r["bat"]
    if r["country"]:
        out["ctry"] = COUNTRY_KO.get(r["country"], r["country"])
    m = re.match(r"(\d+)'\s*(\d+)", str(r["height"]))
    if m:
        out["ht"] = round((int(m.group(1)) * 12 + int(m.group(2))) * 2.54)
    if str(r["weight"]).isdigit():
        out["wt"] = round(int(r["weight"]) * 0.45359237)
    return out or None


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


# ---------------------------------------------------------------- 유형 군집
CL_FEATS = {"투수": ["k_pct", "bb_pct", "hr_pct", "gs_pct"], "타자": ["k_pct", "bb_pct", "hr_pct", "iso", "avg"]}


def _src(rec, use_adj):
    return rec["adj"] if use_adj else rec


def _zvec(rec, role, use_adj, sc):
    s = _src(rec, use_adj)
    return [((s.get(f) if s.get(f) is not None else sc[f][0]) - sc[f][0]) / sc[f][1] for f in CL_FEATS[role]]


def _type_name(role, z, gs_raw):
    """중심점(표준화 값 z)에서 눈에 띄는 특징 2개와 역할로 이름을 만든다. 기준은 |z| >= 0.4."""
    zz = dict(zip(CL_FEATS[role], z))
    cand = []
    if role == "투수":
        if zz["k_pct"] >= .4: cand.append((abs(zz["k_pct"]), "삼진 많은"))
        if zz["k_pct"] <= -.4: cand.append((abs(zz["k_pct"]), "맞혀 잡는"))
        if zz["bb_pct"] <= -.4: cand.append((abs(zz["bb_pct"]), "제구 좋은"))
        if zz["bb_pct"] >= .4: cand.append((abs(zz["bb_pct"]), "볼넷 많은"))
        if zz["hr_pct"] >= .4: cand.append((abs(zz["hr_pct"]), "홈런 맞는"))
        if zz["hr_pct"] <= -.4: cand.append((abs(zz["hr_pct"]), "홈런 억제"))
        tail = "선발형" if gs_raw >= 65 else ("불펜형" if gs_raw <= 25 else "선발·불펜 혼합형")
    else:
        power = (zz["hr_pct"] + zz["iso"]) / 2
        if power >= .4: cand.append((abs(power), "장타력 좋은"))
        if power <= -.4: cand.append((abs(power), "장타력 약한"))
        if zz["k_pct"] <= -.4: cand.append((abs(zz["k_pct"]), "삼진 적은"))
        if zz["k_pct"] >= .4: cand.append((abs(zz["k_pct"]), "삼진 많은"))
        if zz["bb_pct"] >= .4: cand.append((abs(zz["bb_pct"]), "볼넷 많은"))
        if zz["bb_pct"] <= -.4: cand.append((abs(zz["bb_pct"]), "적극적인"))
        if zz["avg"] >= .4: cand.append((abs(zz["avg"]), "타율 높은"))
        if zz["avg"] <= -.4: cand.append((abs(zz["avg"]), "타율 낮은"))
        tail = "타자"
    cand.sort(reverse=True)
    traits = "·".join(t for _, t in cand[:2])
    return (traits + " " + tail) if traits else ("평균적인 " + tail)


def make_types_pitcher(recs, use_adj):
    """투수: 선발(등판 중 선발 비율 50% 이상)과 불펜을 먼저 나누고, 각 그룹 안에서 삼진%·볼넷%·홈런%의 모양으로 3개씩 묶는다.
    z 값과 이름은 같은 그룹 안에서의 상대 위치(예: '선발 중에서 삼진이 많은')다."""
    F = ["k_pct", "bb_pct", "hr_pct"]
    labels, types, used = [None] * len(recs), [], {}
    for gname, cond, gs_raw in (("선발", lambda g: g >= 50, 100.0), ("불펜", lambda g: g < 50, 0.0)):
        idx = [i for i, r in enumerate(recs) if cond(_src(r, use_adj).get("gs_pct") or 0)]
        M = np.array([[(_src(recs[i], use_adj).get(f) if _src(recs[i], use_adj).get(f) is not None else np.nan) for f in F] for i in idx], dtype=float)
        M = np.where(np.isnan(M), np.nanmean(M, axis=0), M)
        mu, sd = M.mean(axis=0), M.std(axis=0, ddof=1)
        Z = (M - mu) / sd
        km = KMeans(n_clusters=3, n_init=10, random_state=0).fit(Z)
        sil = silhouette_score(Z, km.labels_)
        order = np.argsort(-np.bincount(km.labels_))
        for rank, old in enumerate(order):
            tid = len(types)
            members = [idx[j] for j, l in enumerate(km.labels_) if l == old]
            for i in members:
                labels[i] = tid
            z = list(km.cluster_centers_[old]) + [0.0]
            name = _type_name("투수", z, gs_raw)
            used[name] = used.get(name, 0) + 1
            if used[name] > 1:
                name += f" ({chr(64 + used[name])})"
            types.append({"id": tid, "name": name, "size": len(members), "group": gname, "sil": round(float(sil), 2),
                          "z": {f: round(float(v), 2) for f, v in zip(F + ["gs_pct"], z)},
                          "mean": {f: round(float(np.mean([(_src(recs[i], use_adj).get(f) if _src(recs[i], use_adj).get(f) is not None else mu[F.index(f)]) for i in members])), 2) for f in F}
                                  | {"gs_pct": round(float(np.mean([_src(recs[i], use_adj).get("gs_pct") or 0 for i in members])), 1)}})
        print(f"  유형 투수 {'보정' if use_adj else '원본'} {gname}: {len(idx)}명, 실루엣 {sil:.2f}", [t["name"] + f"({t['size']})" for t in types if t["group"] == gname])
    return types, labels


def make_types(role, recs, use_adj, sc):
    """타자: 같은 역할 전체(지난 사례 + 후보)를 K-평균으로 묶는다. k는 3~6 중 실루엣 점수가 가장 높은 값. 투수는 선발/불펜을 먼저 나눈다.
    반환: (유형 목록, 선수별 유형 번호)"""
    if role == "투수":
        return make_types_pitcher(recs, use_adj)
    X = np.array([_zvec(r, role, use_adj, sc) for r in recs])
    best = None
    for k in range(3, 7):
        km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
        s = silhouette_score(X, km.labels_)
        if min(np.bincount(km.labels_)) >= max(15, 0.04 * len(X)) and (best is None or s > best[0] + 1e-9):
            best = (s, k, km)
    s, k, km = best
    order = np.argsort(-np.bincount(km.labels_))  # 큰 유형부터 0,1,2...
    remap = {int(old): new for new, old in enumerate(order)}
    labels = [remap[int(l)] for l in km.labels_]
    types, used = [], {}
    for new, old in enumerate(order):
        z = km.cluster_centers_[old]
        members = [r for r, l in zip(recs, labels) if l == new]
        gs_raw = float(np.mean([(_src(r, use_adj).get("gs_pct") or 0) for r in members])) if role == "투수" else 0
        name = _type_name(role, z, gs_raw)
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            name += f" ({chr(64 + used[name])})"
        mean = {f: float(np.mean([(_src(r, use_adj).get(f) if _src(r, use_adj).get(f) is not None else sc[f][0]) for r in members])) for f in CL_FEATS[role]}
        types.append({"id": new, "name": name, "size": len(members), "sil": round(float(s), 2), "z": {f: round(float(v), 2) for f, v in zip(CL_FEATS[role], z)},
                      "mean": {f: round(v, 2) for f, v in mean.items()}})
    print(f"  유형 {role} {'보정' if use_adj else '원본'}: k={k}, 실루엣 {s:.2f}", [t["name"] + f"({t['size']})" for t in types])
    return types, labels


# ---------------------------------------------------------------- 검증 (교차검증)
def _succ(rec, crit, p_ip=144, p_era=3.5, b_ab=446, b_ops=0.85):
    role, y = rec["역할"], rec["KBO첫해"]
    def first(r):
        if role == "투수":
            return r.get("KBO_이닝") is not None and r.get("KBO_ERA") is not None and r["KBO_이닝"] >= p_ip and r["KBO_ERA"] <= p_era
        return r.get("KBO_타수") is not None and r.get("KBO_OPS") is not None and r["KBO_타수"] >= b_ab and r["KBO_OPS"] >= b_ops
    if crit == "first":
        return first(rec)
    if y >= POOL_YEAR:
        return None  # 2026 입단자는 다음 해 기록이 없어 제외
    if crit == "stay":
        return rec.get("다음해_KBO") == "있음"
    if crit == "first+stay":
        return first(rec) and rec.get("다음해_KBO") == "있음"
    k = rec.get("kbo") or []
    a = next((x for x in k if x["y"] == y), None)
    b = next((x for x in k if x["y"] == y + 1), None)
    if not a or not b:
        return False
    if role == "투수":
        ip = (a["IP"] or 0) + (b["IP"] or 0)
        if not ip:
            return False
        era = ((a["ERA"] or 0) * (a["IP"] or 0) + (b["ERA"] or 0) * (b["IP"] or 0)) / ip
        return ip >= 2 * p_ip and era <= p_era
    ab = (a["AB"] or 0) + (b["AB"] or 0)
    if not ab:
        return False
    ops = ((a["OPS"] or 0) * (a["AB"] or 0) + (b["OPS"] or 0) * (b["AB"] or 0)) / ab
    return ab >= 2 * b_ab and ops >= b_ops


N_PERM = 100


def _oof_auc(X, y):
    """교차검증으로 예측한 값의 AUC (로지스틱 회귀, 5-최근접)"""
    pr, knn = oof_predictions(X, y)
    return roc_auc_score(y, pr), roc_auc_score(y, knn)


def oof_predictions(X, y):
    """5-겹 층화 교차검증을 10번 반복해, 선수마다 '그 선수를 학습에서 뺀 모델'의 예측 평균을 만든다.
    (한 명씩 빼는 LOO는 신호가 없을 때 AUC가 0.5보다 훨씬 낮게 나오는 착시가 있어 쓰지 않는다.)
    pr: 로지스틱 회귀, knn: 학습 쪽에서 가장 가까운 5명의 성공 비율(화면의 '닮은 사례 5명'과 같은 방식)"""
    n = len(y)
    pr, knn, cnt = np.zeros(n), np.zeros(n), np.zeros(n)
    for tr, te in RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=0).split(X, y):
        clf = LogisticRegression(C=1.0, max_iter=2000).fit(X[tr], y[tr])
        pr[te] += clf.predict_proba(X[te])[:, 1]
        d2 = ((X[te][:, None, :] - X[tr][None, :, :]) ** 2).sum(-1)
        knn[te] += y[tr][np.argsort(d2, axis=1)[:, :5]].mean(axis=1)
        cnt[te] += 1
    return pr / cnt, knn / cnt


def run_validation(past, scale, scale_adj):
    """입단 전 5년 지표(5개)로 KBO 성공 여부를 얼마나 가릴 수 있는지: 로지스틱 회귀와 5-최근접(화면에서 쓰는 방식)을
    5-겹 교차검증 10회 반복으로 예측한 뒤 AUC(1=완벽). 교차검증 AUC는 신호가 없어도 0.5보다 낮게 나오는 편향이 있어서,
    라벨을 섞은 자료로 같은 절차를 100번 돌린 AUC 분포(null)와 비교한다. p값 = 섞은 자료에서 관측값 이상이 나온 비율.
    uni = 지표 하나씩의 AUC(0.5=무관)와 맨-휘트니 검정 p값(교차검증 편향 없음)."""
    rng = np.random.default_rng(0)
    res = []
    for role in ("투수", "타자"):
        feats = TRAD[role]
        for mode in ("raw", "adj"):
            sc = scale_adj[role] if mode == "adj" else scale[role]
            recs = [r for r in past if r["역할"] == role]
            for crit in ("first", "stay", "first+stay", "two"):
                rows = [(r, _succ(r, crit)) for r in recs]
                rows = [(r, int(bool(s))) for r, s in rows if s is not None]
                y = np.array([s for _, s in rows])
                n, pos = len(y), int(y.sum())
                if pos < 6 or n - pos < 6:
                    res.append({"role": role, "feat": mode, "crit": crit, "n": n, "pos": pos})
                    continue
                X = np.array([[((_src(r, mode == "adj").get(f) if _src(r, mode == "adj").get(f) is not None else sc[f][0]) - sc[f][0]) / sc[f][1] for f in feats] for r, _ in rows])
                a1, a2 = _oof_auc(X, y)
                # 같은 절차를 라벨을 섞어서 N_PERM번 돌려 "아무 관계도 없을 때 이 절차가 내는 AUC"의 분포를 만든다
                null = np.array([_oof_auc(X, rng.permutation(y)) for _ in range(N_PERM)])
                uni = {}
                for i, f in enumerate(feats):
                    u = roc_auc_score(y, X[:, i])
                    uni[f] = [round(float(u), 3), round(float(mannwhitneyu(X[y == 1, i], X[y == 0, i]).pvalue), 3)]
                res.append({"role": role, "feat": mode, "crit": crit, "n": n, "pos": pos,
                            "lr": round(a1, 3), "lr_null": round(float(null[:, 0].mean()), 3),
                            "lr_lo": round(float(np.percentile(null[:, 0], 2.5)), 3), "lr_hi": round(float(np.percentile(null[:, 0], 97.5)), 3),
                            "lr_p": round((1 + int((null[:, 0] >= a1).sum())) / (1 + N_PERM), 3),
                            "knn": round(a2, 3), "knn_null": round(float(null[:, 1].mean()), 3),
                            "knn_lo": round(float(np.percentile(null[:, 1], 2.5)), 3), "knn_hi": round(float(np.percentile(null[:, 1], 97.5)), 3),
                            "knn_p": round((1 + int((null[:, 1] >= a2).sum())) / (1 + N_PERM), 3),
                            "uni": uni})
    return res


def main():
    co = pd.read_csv("data/kbo_cohort.csv", dtype=str).fillna("")
    global ARS
    if os.path.exists("data/il_stints.csv"):
        ilf = pd.read_csv("data/il_stints.csv")
        IL.update({int(k): g for k, g in ilf.groupby("id")})
    if os.path.exists("data/pitch_arsenal.csv"):
        ARS = pd.read_csv("data/pitch_arsenal.csv")
    lgdf = pd.read_csv("data/league_rates.csv")
    for _, x in lgdf.iterrows():
        LG[(int(x["season"]), x["level"])] = x
    kn = {}  # mykbo_id -> 한국 등록명 (09번이 MyKBO 선수 페이지에서 받음. 없으면 빈 칸)
    if os.path.exists("data/kbo_korean_names.csv"):
        k = pd.read_csv("data/kbo_korean_names.csv", dtype=str).fillna("")
        kn = dict(zip(k["mykbo_id"], k["한국등록명"]))
    waivers = []  # 웨이버 공시·방출 사례 (11번이 기사에서 확인한 것만. 전체 목록이 아님)
    if os.path.exists("data/kbo_waivers.csv"):
        waivers = pd.read_csv("data/kbo_waivers.csv", dtype=str).fillna("").to_dict("records")
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
        adjp = prof.pop("adj")
        rec = {"KBO첫해": debut, "mykbo_id": r["mykbo_id"], "영문명": r["영문명"], "한글명": kn.get(r["mykbo_id"], ""), "팀": r["팀"], "역할": role,
               "mlbam": int(r["mlbam"]), "창": prof.pop("years"), **{k: clean(v) for k, v in prof.items()},
               "adj": {k: clean(v) for k, v in adjp.items()}}
        flags = [note] if note else []
        if "확인 필요" in r["연결방법"]:
            flags.append("이름 연결: " + r["연결방법"])
        if rec["mlb_share"] < 0.2:
            flags.append("MLB 비중이 낮음(트리플A 위주)")
        rec["주의"] = " / ".join(flags)
        rec["hist"] = hist_rows(role, h, debut - WINDOW, debut - 1)
        rec["il"] = il_summary(r["mlbam"], debut - WINDOW, debut - 1)
        if role == "투수":
            a = arsenal_of(r["mlbam"], debut - WINDOW, debut - 1)
            if a:
                rec["ars"] = a
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
        adjp = prof.pop("adj")
        rec = {"player_id": int(c["player_id"]), "player_name": c["player_name"], "한글명": mlb_ko.get(int(c["player_id"]), ""),
               "역할": role, "창": prof.pop("years"),
               **{k: clean(v) for k, v in prof.items()}, "adj": {k: clean(v) for k, v in adjp.items()}, "total_pitches": int(c["total_pitches"]), "pa26": int(c["pa"]),
               "MLB_공수": int(c["MLB_공수"]), "소속": c["소속"],
               "KBO경력": 1 if (name_flag or int(c["player_id"]) in cand_ids) else 0, "주의": note}
        rec["hist"] = hist_rows(role, h, POOL_YEAR - WINDOW + 1, POOL_YEAR)
        rec["il"] = il_summary(c["player_id"], POOL_YEAR - WINDOW + 1, POOL_YEAR)
        if role == "투수":
            a = arsenal_of(c["player_id"], POOL_YEAR - WINDOW + 1, POOL_YEAR)
            if a:
                rec["ars"] = a
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
        b = bio_of(people, r["mlbam"])
        if b:
            r["bio"] = b
    for c in cands:
        c["출생연도"] = by(c["player_id"])
        b = bio_of(people, c["player_id"])
        if b:
            c["bio"] = b

    # ---------- 표준화 기준: 지난 사례 + 후보 전체
    scale = {}
    for role, feats in TRAD.items():
        allp = [r for r in past + cands if r["역할"] == role]
        scale[role] = {f: [float(np.mean([r[f] for r in allp])), float(np.std([r[f] for r in allp], ddof=1))] for f in feats}
    scale_adj = {}
    for role, feats in TRAD.items():
        allp = [r["adj"] for r in past + cands if r["역할"] == role]
        scale_adj[role] = {}
        for f in feats:
            v = [a[f] for a in allp if a.get(f) is not None]
            scale_adj[role][f] = [float(np.mean(v)), float(np.std(v, ddof=1))]
    # ---------- 유형 군집 (원본 지표 기준 / 환경 보정 지표 기준 각각)
    types = {"raw": {}, "adj": {}}
    for role in TRAD:
        recs = [r for r in past + cands if r["역할"] == role]
        for mode, use_adj, sc in (("raw", False, scale[role]), ("adj", True, scale_adj[role])):
            tl, labels = make_types(role, recs, use_adj, sc)
            types[mode][role] = tl
            for r, l in zip(recs, labels):
                r["typ" if mode == "raw" else "typA"] = int(l)
    # ---------- 교차검증
    print("교차검증 계산 중...", flush=True)
    validation = run_validation(past, scale, scale_adj)
    sdf = sav[(sav["레벨"] == "AAA")]
    sscale = {}
    for role, feats in SC.items():
        d = sdf[sdf["role"] == ROLE_EN[role]]
        d = d[d["total_pitches"] >= 500] if role == "투수" else d[d["pa"] >= 150]
        sscale[role] = {f: [float(d[f].mean()), float(d[f].std())] for f in feats}

    out = {"만든날": time.strftime("%Y-%m-%d"), "후보연도": POOL_YEAR, "창길이": WINDOW, "feats": TRAD, "scale": scale, "scaleAdj": scale_adj,
           "sfeats": SC, "sscale": sscale, "past": {}, "cands": {}, "excluded": {}, "waivers": waivers,
           "types": types, "validation": validation}
    for role in TRAD:
        out["past"][role] = [r for r in past if r["역할"] == role]
        out["cands"][role] = [c for c in cands if c["역할"] == role]
        out["excluded"][role] = [e for e in excluded if e["역할"] == role]
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.js", "w", encoding="utf-8") as f:
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
    print("docs/data.js", os.path.getsize("docs/data.js"), "bytes")
    print({r: {f: [round(a, 2) for a in v] for f, v in s.items()} for r, s in scale.items()})


if __name__ == "__main__":
    main()
