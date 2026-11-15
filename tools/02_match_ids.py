"""2단계: 명단(data/kbo_foreign_players.csv)의 영문 이름을 스탯캐스트 선수 번호(MLBAM)에 연결한다.

실행:  pip install pandas
       python tools/02_match_ids.py

하는 일:
  - 체드윅 선수 명부(github.com/chadwickbureau/register)를 data/raw/chadwick/에 한 번 받는다(약 65MB).
  - 영문 이름(악센트 제거, 대소문자 무시)이 같은 사람을 찾아 번호를 붙인다.
  - 같은 이름이 여러 명이면 번호를 정하지 않고 후보 번호를 모두 적는다(3단계 이후 스탯캐스트 기록으로 고른다).
  - 결과: data/kbo_foreign_matched.csv  (+ 화면에 못 찾은 이름 목록)

주의: 이름이 같다고 같은 사람은 아니다. 한 명만 나온 경우도 출생연도가 이상하면 직접 확인한다.
"""
import os
import re
import unicodedata

import pandas as pd

CH_DIR = "data/raw/chadwick"
CH_URL = "https://raw.githubusercontent.com/chadwickbureau/register/master/data/people-{}.csv"
SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z ]", " ", s).lower()
    return " ".join(w for w in s.split() if w not in SUFFIXES)


def load_register() -> pd.DataFrame:
    os.makedirs(CH_DIR, exist_ok=True)
    frames = []
    for h in "0123456789abcdef":
        path = os.path.join(CH_DIR, f"people-{h}.csv")
        if not os.path.exists(path):
            import requests
            r = requests.get(CH_URL.format(h), timeout=120)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
        frames.append(pd.read_csv(path, dtype=str, usecols=[
            "key_mlbam", "name_first", "name_last", "name_given", "birth_year",
            "pro_played_first", "pro_played_last", "mlb_played_last"]))
    df = pd.concat(frames, ignore_index=True)
    df = df[df["key_mlbam"].notna()].copy()
    df["full"] = (df["name_first"].fillna("") + " " + df["name_last"].fillna("")).map(norm)
    df["last_year"] = pd.to_numeric(df["pro_played_last"], errors="coerce")
    return df


def main():
    roster = pd.read_csv("data/kbo_foreign_players.csv", encoding="utf-8-sig")
    reg = load_register()
    name_col = "영문명(확인 필요)"
    rows = []
    for _, r in roster.iterrows():
        en = r.get(name_col)
        out = r.to_dict()
        out.update(mlbam="", 출생연도="", 마지막_프로시즌="", 후보수=0, 동명이인="", 후보번호="", 후보출생연도="", 매칭결과="")
        if pd.isna(en) or not str(en).strip():
            out["매칭결과"] = "영문명 없음"
        else:
            hit = reg[reg["full"] == norm(en)].sort_values("last_year", ascending=False)
            out["후보수"] = len(hit)
            if hit.empty:
                out["매칭결과"] = "못 찾음"
            else:
                if len(hit) == 1:
                    top = hit.iloc[0]
                    out.update(mlbam=top["key_mlbam"], 출생연도=top["birth_year"],
                               마지막_프로시즌=top["pro_played_last"], 매칭결과="찾음")
                else:
                    # 동명이인: 임의로 고르지 않는다. 후보 번호를 모두 적고, 스탯캐스트 기록이 있는 쪽을 3단계 이후에 고른다.
                    out.update(mlbam="", 매칭결과="동명이인(후보 여러 명)", 동명이인="있음",
                               후보번호="|".join(hit["key_mlbam"]),
                               후보출생연도="|".join(hit["birth_year"].fillna("?")))
        rows.append(out)
    res = pd.DataFrame(rows)
    res.to_csv("data/kbo_foreign_matched.csv", index=False, encoding="utf-8-sig")
    print(res["매칭결과"].value_counts().to_string())
    bad = res[res["매칭결과"] != "찾음"]
    if len(bad):
        print("\n[못 찾았거나 영문명 없음]")
        print(bad[["시즌", "팀", "선수(기사 표기)", name_col, "매칭결과"]].to_string())
    dup = res[res["동명이인"] == "있음"]
    if len(dup):
        print("\n[동명이인 - 번호를 아직 정하지 않음]")
        print(dup[["시즌", "팀", name_col, "후보번호", "후보출생연도"]].to_string())


if __name__ == "__main__":
    main()
