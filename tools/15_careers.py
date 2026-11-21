"""15단계: 선수 경력(연도·레벨·팀)과 "함께 뛴 사람" 정보를 만들어 docs/careers.js 로 내보낸다. (상세 창의 History 보기가 읽는다)

실행:  python -I tools/15_careers.py
입력:  data/kbo_cohort.csv (07번, 지난 사례의 mlbam), data/candidates_2026.csv (03번, 2026 후보),
       data/kbo_foreign_seasons.csv (05번, KBO 외국인 시즌), data/kbo_korean_names.csv (09번, 한국 등록명),
       data/korean_names_extra.csv (직접 적은 한국인 선수 한글 이름)
결과:  data/raw/careers/  받은 원본 캐시 (git 제외)
       data/careers.csv        선수·시즌·레벨별 소속팀 (MLB 공식 Stats API)
       data/korean_born.csv    한국에서 태어난 미국 프로(MLB·마이너) 선수 명단
       docs/careers.js         화면용. window.CAREERS = {선수번호: {...}}

만드는 것
1. 경력: 선수마다 시즌·레벨(MLB/AAA/AA/A+/A/R)·팀. 마이너 팀의 모구단(parent org)도 붙인다.
2. 겹침(재미 요소): "같은 시즌에 같은 팀(팀 번호가 같음)에서 기록이 있는" 사람을 찾는다.
   - KBO 외국인: data/kbo_cohort.csv 에서 미국 기록과 연결된 선수(2015~2026 입단) 가운데 겹치는 사람.
   - 코리안리거: 한국에서 태어난 MLB·마이너 선수.
   "함께 뛰었다"는 같은 시즌 같은 팀에 이름이 있다는 뜻이다. 같은 날 같이 로스터에 있었는지는 알 수 없다.

주의
- 한국 출생 선수 목록은 출생지 기준이다. 한국계 미국인(입양 등)도 섞일 수 있어서 data/korean_exclude.csv 에 적은 번호는 뺀다.
- 규칙: 선수 100명씩 묶어 보내고 사이에 2초 쉰다. 이미 받은 (레벨, 선수)는 다시 받지 않는다.
"""
import json
import os
import sys
import time
from collections import defaultdict

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

B = "https://statsapi.mlb.com/api/v1"
H = {"User-Agent": "Mozilla/5.0 (research script)"}
RAW = "data/raw/careers"
SPORTS = {1: "MLB", 11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A-", 16: "R"}
ORDER = {"MLB": 0, "AAA": 1, "AA": 2, "A+": 3, "A": 4, "A-": 5, "R": 6}
KR_SEASONS = range(2008, 2027)
MAX_LIST = 6  # 겹침 목록은 종류별로 이만큼만 담는다


def get(url, params, tries=3):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=H, timeout=180)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(3 * (k + 1))


# ---------------------------------------------------------------- 경력 받기
def fetch_careers(ids):
    os.makedirs(RAW, exist_ok=True)
    rows_path, done_path, ppl_path = f"{RAW}/rows.csv", f"{RAW}/fetched.txt", f"{RAW}/people.csv"
    done = set(open(done_path, encoding="utf-8").read().split()) if os.path.exists(done_path) else set()
    cols = ["id", "season", "level", "team_id", "team"]
    new_rows = 0
    for sp, lv in SPORTS.items():
        todo = [i for i in sorted(ids) if f"{sp}:{i}" not in done]
        for k in range(0, len(todo), 100):
            chunk = todo[k:k + 100]
            j = get(f"{B}/people", {"personIds": ",".join(map(str, chunk)),
                                    "hydrate": f"stats(group=[pitching,hitting],type=[yearByYear],sportId={sp})"})
            rows, ppl = [], []
            for p in j.get("people", []):
                ppl.append({"id": p["id"], "name": p.get("fullName", ""), "birthDate": p.get("birthDate", ""),
                            "mlbDebutDate": p.get("mlbDebutDate", ""), "birthCountry": p.get("birthCountry", "")})
                for blk in p.get("stats", []):
                    for s in blk.get("splits", []):
                        t = s.get("team") or {}
                        if not t.get("id") or not s.get("season"):
                            continue  # 이적 합계 줄 등
                        rows.append({"id": p["id"], "season": int(str(s["season"]).split(".")[0]), "level": lv, "team_id": t["id"], "team": t.get("name", "")})
            if rows:
                pd.DataFrame(rows, columns=cols).to_csv(rows_path, mode="a", index=False, header=not os.path.exists(rows_path), encoding="utf-8-sig")
            if ppl and sp == 1:
                pd.DataFrame(ppl).to_csv(ppl_path, mode="a", index=False, header=not os.path.exists(ppl_path), encoding="utf-8-sig")
            with open(done_path, "a", encoding="utf-8") as f:
                f.write("".join(f"{sp}:{i}\n" for i in chunk))
            new_rows += len(rows)
            print(f"{lv} {k + len(chunk)}/{len(todo)}명 처리, 새 기록 {len(rows)}줄", flush=True)
            time.sleep(2)
    return new_rows


def load_careers():
    c = pd.read_csv(f"{RAW}/rows.csv", encoding="utf-8-sig").drop_duplicates(["id", "season", "level", "team_id"])
    p = pd.read_csv(f"{RAW}/people.csv", encoding="utf-8-sig").drop_duplicates("id").set_index("id")
    return c, p


# ---------------------------------------------------------------- 한국 출생 선수 찾기
def find_korean_born():
    os.makedirs(RAW, exist_ok=True)
    path, done_path = f"{RAW}/korean_born_raw.csv", f"{RAW}/korean_scan.txt"
    done = set(open(done_path, encoding="utf-8").read().split()) if os.path.exists(done_path) else set()
    for sp in SPORTS:
        for y in KR_SEASONS:
            key = f"{sp}:{y}"
            if key in done:
                continue
            j = get(f"{B}/sports/{sp}/players", {"season": y})
            kr = [{"id": p["id"], "name": p.get("fullName", ""), "birthDate": p.get("birthDate", ""), "birthCountry": p.get("birthCountry", "")}
                  for p in j.get("people", []) if "korea" in (p.get("birthCountry") or "").lower()]
            if kr:
                pd.DataFrame(kr).to_csv(path, mode="a", index=False, header=not os.path.exists(path), encoding="utf-8-sig")
            with open(done_path, "a", encoding="utf-8") as f:
                f.write(key + "\n")
            print(f"한국 출생 찾기 {SPORTS[sp]} {y}: {len(kr)}명", flush=True)
            time.sleep(1.5)
    k = pd.read_csv(path, encoding="utf-8-sig").drop_duplicates("id")
    return k


# ---------------------------------------------------------------- 모구단 정보
def load_parents(seasons):
    path = f"{RAW}/parents.csv"
    have = pd.read_csv(path, encoding="utf-8-sig") if os.path.exists(path) else pd.DataFrame(columns=["season", "team_id", "parent"])
    need = [y for y in sorted(seasons) if y not in set(have["season"])]
    rows = []
    for y in need:
        j = get(f"{B}/teams", {"sportIds": ",".join(map(str, SPORTS)), "season": y})
        for t in j.get("teams", []):
            rows.append({"season": y, "team_id": t["id"], "parent": t.get("parentOrgName") or ""})
        print(f"팀 모구단 {y}: {len(j.get('teams', []))}팀", flush=True)
        time.sleep(1.5)
    if rows:
        have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
        have.to_csv(path, index=False, encoding="utf-8-sig")
    return {(int(r.season), int(r.team_id)): r.parent for r in have.itertuples()}


# ---------------------------------------------------------------- 만들기
def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    co = pd.read_csv("data/kbo_cohort.csv", encoding="utf-8-sig")
    cands = pd.read_csv("data/candidates_2026.csv", encoding="utf-8-sig")
    linked = co[co["mlbam"].notna()].copy()
    linked["mlbam"] = linked["mlbam"].astype(int)
    subjects = set(linked["mlbam"]) | set(int(x) for x in cands["player_id"])

    kr = find_korean_born()
    excl = set()
    if os.path.exists("data/korean_exclude.csv"):
        excl = set(pd.read_csv("data/korean_exclude.csv", encoding="utf-8-sig")["id"].astype(int))
    kr = kr[~kr["id"].isin(excl)]
    print("한국 출생 선수:", len(kr), "명 (제외", len(excl), "명)")

    all_ids = subjects | set(int(i) for i in kr["id"])
    print("경력을 받을 선수:", len(all_ids), "명")
    fetch_careers(all_ids)
    car, ppl = load_careers()
    parents = load_parents(set(car["season"]))
    car["parent"] = [parents.get((int(s), int(t)), "") for s, t in zip(car["season"], car["team_id"])]
    car.sort_values(["id", "season", "level"], key=lambda c: c.map(ORDER) if c.name == "level" else c).to_csv("data/careers.csv", index=False, encoding="utf-8-sig")
    # 코리안리거는 트리플A 이상에 오른 한국 출생 선수만 쓴다(루키·싱글A 선수까지 넣으면 어수선하다)
    reach = set(car[car["level"].isin(["MLB", "AAA"])]["id"])
    kr = kr[kr["id"].isin(reach)]
    print("코리안리거(트리플A 이상):", len(kr), "명")
    kr.to_csv("data/korean_born.csv", index=False, encoding="utf-8-sig")

    # 한글 이름
    ko = pd.read_csv("data/kbo_korean_names.csv", encoding="utf-8-sig", dtype=str).fillna("")
    ko_by_myk = {r.mykbo_id: r.한국등록명 for r in ko.itertuples() if r.한국등록명}
    kn = {}
    if os.path.exists("data/korean_names_extra.csv"):
        kn = {int(r.id): r.name_ko for r in pd.read_csv("data/korean_names_extra.csv", encoding="utf-8-sig", dtype={"id": int}).itertuples()}

    # KBO 외국인(미국 기록과 연결된 사람) 정보
    kbo_seasons = pd.read_csv("data/kbo_foreign_seasons.csv", dtype=str, encoding="utf-8-sig").fillna("")
    kbo_seasons["연도"] = kbo_seasons["연도"].astype(int)
    kbo_by_myk = defaultdict(list)
    for r in kbo_seasons.itertuples():
        kbo_by_myk[r.mykbo_id].append((r.연도, r.팀))
    F = {}
    for r in linked.itertuples():
        yrs = sorted(kbo_by_myk.get(str(r.mykbo_id), []))
        F[int(r.mlbam)] = {"myk": str(r.mykbo_id), "en": r.영문명, "ko": ko_by_myk.get(str(r.mykbo_id), ""), "role": r.역할,
                           "first": int(r.KBO첫해), "last": yrs[-1][0] if yrs else int(r.KBO첫해)}

    # (시즌, 팀 번호) → 그 팀에 이름이 있는 선수들
    by_team = defaultdict(set)
    for r in car.itertuples():
        by_team[(int(r.season), int(r.team_id))].add(int(r.id))
    kr_ids = set(int(i) for i in kr["id"])
    kr_name = {int(r.id): r.name for r in kr.itertuples()}
    team_of = {(int(r.id), int(r.season), int(r.team_id)): r.team for r in car.itertuples()}

    out = {}
    TN, TI = [], {}    # 팀 이름 목록(번호로 가리켜 용량을 줄인다)
    LVN = list(ORDER)  # 레벨 번호: 0=MLB ... 6=R

    def tix(name):
        if not name:
            return -1
        if name not in TI:
            TI[name] = len(TN)
            TN.append(name)
        return TI[name]

    g = {i: d for i, d in car.groupby("id")}
    for pid in subjects:
        d = g.get(pid)
        if d is None:
            continue
        seasons = defaultdict(list)
        for r in d.itertuples():
            seasons[int(r.season)].append([r.level, r.team, r.parent if r.level != "MLB" else ""])
        st = [[y, [[LVN.index(x[0]), tix(x[1]), tix(x[2])] for x in sorted(v, key=lambda x: ORDER[x[0]])]] for y, v in sorted(seasons.items())]

        def overlaps(pool):
            """겹친 사람 → {팀 이름: {함께한 시즌}}"""
            hit = defaultdict(lambda: defaultdict(set))
            for r in d.itertuples():
                for o in by_team[(int(r.season), int(r.team_id))]:
                    if o != pid and o in pool:
                        hit[o][r.team].add(int(r.season))
            return hit

        def pack(v):
            """팀별 [팀, [시즌...]] (오래 함께한 팀, 최근 팀 순)와 함께한 시즌 수"""
            ty = sorted(([t, sorted(ys)] for t, ys in v.items()), key=lambda x: (-len(x[1]), -x[1][-1]))
            return ty[:3], len({y for ys in v.values() for y in ys}), max(y for ys in v.values() for y in ys)

        fk = []
        for o, v in overlaps(set(F) - {pid}).items():
            f = F[o]; ty, n, last = pack(v)
            fk.append({"id": f["myk"], "role": f["role"], "en": f["en"], "ko": f["ko"], "ty": ty, "n": n, "last": last, "kbo": [f["first"], f["last"]]})
        fk.sort(key=lambda x: (-x["n"], -x["last"]))
        kl = []
        for o, v in overlaps(kr_ids - {pid}).items():
            ty, n, last = pack(v)
            kl.append({"id": o, "en": kr_name.get(o, ""), "ko": kn.get(o, ""), "ty": ty, "n": n, "last": last})
        kl.sort(key=lambda x: (-x["n"], -x["last"]))

        pr = ppl.loc[pid] if pid in ppl.index else None
        out[str(pid)] = {
            "md": (pr["mlbDebutDate"] if pr is not None and isinstance(pr["mlbDebutDate"], str) else ""),
            "st": st,
            "fk": fk[:MAX_LIST], "nfk": len(fk),
            "kl": kl[:MAX_LIST], "nkl": len(kl),
        }
    with open("docs/careers.js", "w", encoding="utf-8") as f:
        f.write("// tools/15_careers.py 가 만든 파일. 직접 고치지 않는다. T=팀 이름 목록, L=레벨 이름, P=선수번호별 자료(st 안의 [레벨, 팀, 모구단]은 번호)\nwindow.CAREERS = ")
        json.dump({"T": TN, "L": LVN, "P": out}, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    n_fk = sum(1 for v in out.values() if v["fk"]); n_kl = sum(1 for v in out.values() if v["kl"])
    print(f"docs/careers.js: 선수 {len(out)}명, KBO 외국인 겹침 {n_fk}명, 코리안리거 겹침 {n_kl}명,",
          os.path.getsize("docs/careers.js"), "바이트")


if __name__ == "__main__":
    main()
