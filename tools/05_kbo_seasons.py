"""5단계: KBO 외국인 선수의 시즌 성적을 MyKBO Stats에서 받는다.

실행:  python tools/05_kbo_seasons.py
출처:  https://mykbostats.com/players/foreign/<연도>  (연도별 외국인 선수 목록 + 그 해 성적)
결과:  data/raw/mykbo/foreign_<연도>.html   받은 원본 (git 제외)
       data/kbo_foreign_seasons.csv         연도·선수마다 한 줄 (투수·타자 성적)

이 사이트를 쓰는 근거 (2026-11-15 확인)
- robots.txt: /stats/compare/ 만 금지, 요청 사이 5초 쉬라고 적혀 있음 → 6초 쉰다.
- 이용약관(/tos): 자동 도구 사용 허용, 과도한 요청 금지 → 연도별 1쪽씩, 모두 13쪽만 받는다.
- 사진·로고는 받지 않는다. 숫자와 이름만 쓴다.

주의
- "KBO첫해"는 이 사이트 목록(2014년~)에 처음 나온 해다. 2014년 이전에 뛴 적이 있는지는 알 수 없어
  2014년은 첫해 여부를 비워 둔다.
- 한 해에 팀을 옮긴 선수는 줄이 여러 개일 수 있다.
- 이미 받은 원본은 다시 받지 않는다. 다시 받으려면 파일을 지운다.
"""
import html
import os
import re
import time

import pandas as pd
import requests

BASE = "https://mykbostats.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (research script)"}
OUT = "data/raw/mykbo"
YEARS = range(2014, 2027)

PITCH_COLS = ["W-L-SV", "ERA", "WHIP", "G", "GS", "QS", "IP", "R", "ER", "H", "HR", "SO", "BB", "K/BB"]
HIT_COLS = ["AVG", "OBP", "SLG", "OPS", "G", "AB", "H", "R", "HR", "RBI", "BB", "IBB", "SO", "BB/K"]


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def fetch(year):
    path = os.path.join(OUT, f"foreign_{year}.html")
    if os.path.exists(path):
        return open(path, encoding="utf-8").read(), "이미 있음"
    r = requests.get(f"{BASE}/players/foreign/{year}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    r.encoding = "utf-8"
    with open(path, "w", encoding="utf-8") as f:
        f.write(r.text)
    time.sleep(6)
    return r.text, r.status_code


def parse(page, year):
    rows = []
    page = re.sub(r"(?s)<!--.*?-->", "", page)  # 주석 처리된 칸(키·몸무게 등)은 뺀다
    for table in re.findall(r"(?s)<table.*?</table>", page):
        head = re.search(r'<thead name="(pitchers|hitters)"', table)
        if not head:
            continue
        kind = head.group(1)
        cols = PITCH_COLS if kind == "pitchers" else HIT_COLS
        body = table.split("</thead>", 1)[1]
        for tr in re.findall(r"(?s)<tr.*?</tr>", body):
            link = re.search(r'href="/players/(\d+)"', tr)
            cells = re.findall(r"(?s)<td([^>]*)>(.*?)</td>", tr)
            if not link or len(cells) != len(cols) + 2:
                continue
            name = text(re.findall(r'(?s)<a class="player-link" [^>]*>(.*?)</a>', tr)[-1])
            row = {"연도": year, "mykbo_id": link.group(1), "영문명": name,
                   "팀": text(cells[1][1]), "역할": "투수" if kind == "pitchers" else "타자"}
            for col, (attrs, val) in zip(cols, cells[2:]):
                key = ("투_" if kind == "pitchers" else "타_") + col
                row[key] = text(val)
                if col == "IP":  # 이닝은 아웃 수로도 적는다 (33⅔이닝 = 101아웃)
                    outs = re.search(r'data-sort-value="(\d+)"', attrs)
                    row["투_아웃수"] = outs.group(1) if outs else ""
            rows.append(row)
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for year in YEARS:
        try:
            page, status = fetch(year)
            got = parse(page, year)
            rows += got
            print(year, status, "투수", sum(r["역할"] == "투수" for r in got),
                  "타자", sum(r["역할"] == "타자" for r in got), flush=True)
        except Exception as e:
            print(year, "실패", repr(e)[:150], flush=True)

    # 2010~2013년 목록은 MyKBO에 일부만 있다(투수 1·6·10·20명, 타자 0명). 표본으로는 못 쓰고,
    # "이미 그 전에 KBO에서 뛴 사람"을 걸러내는 이름 명단으로만 쓴다.
    pre = []
    for year in range(2010, 2014):
        try:
            page, status = fetch(year)
            got = parse(page, year)
            pre += got
            print(year, status, "(부분 명단) 투수", sum(r["역할"] == "투수" for r in got), "타자", sum(r["역할"] == "타자" for r in got), flush=True)
        except Exception as e:
            print(year, "실패", repr(e)[:150], flush=True)
    pd.DataFrame(pre)[["연도", "mykbo_id", "영문명", "팀", "역할"]].to_csv("data/kbo_foreign_pre2014.csv", index=False, encoding="utf-8-sig")

    df = pd.DataFrame(rows)
    # 투수도 타석에 서면 타자 표에 나온다. 그 해 던진 아웃 수가 타수보다 많으면 주역할을 투수로 본다.
    outs = pd.to_numeric(df["투_아웃수"], errors="coerce").fillna(0).groupby([df["연도"], df["mykbo_id"]]).transform("sum")
    ab = pd.to_numeric(df["타_AB"], errors="coerce").fillna(0).groupby([df["연도"], df["mykbo_id"]]).transform("sum")
    df.insert(5, "주역할", (outs > ab).map({True: "투수", False: "타자"}))
    first = df.groupby("mykbo_id")["연도"].transform("min")
    unknown = first == min(YEARS)
    df.insert(6, "KBO첫해", first.astype(str).where(~unknown, ""))
    df.insert(7, "첫해여부", (df["연도"] == first).map({True: "첫해", False: ""}).where(~unknown, "알 수 없음(2014 이전 가능)"))
    df.to_csv("data/kbo_foreign_seasons.csv", index=False, encoding="utf-8-sig")
    print("=" * 70)
    print("모두", len(df), "줄 / 선수", df["mykbo_id"].nunique(), "명")
    main_rows = df[(df["첫해여부"] == "첫해") & (df["역할"] == df["주역할"])]
    print("첫해 선수 수(주역할 기준):")
    print(main_rows.drop_duplicates(["연도", "mykbo_id"]).groupby(["연도", "주역할"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
