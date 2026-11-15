"""3단계: 2023~2026 시즌별 스탯캐스트(선수별 묶음)를 받는다.

실행:  python tools/03_download_seasons.py
결과:  data/raw/seasons/ 아래에 CSV, 화면에 파일별 상태(응답 코드, 행 수)

받는 것: 트리플A 투수·타자(2023~2026), 메이저리그 투수·타자(2023~2026)
         (트리플A 스탯캐스트는 2023년부터 있는 것으로 알고 있으나 이 스크립트로 처음 확인한다)

주의: 작성자가 직접 실행해 보지 못했다(사이트 접속이 막힌 환경).
      01번에서 확인된 주소는 트리플A 2026 투수·타자 두 가지뿐이다. 나머지는 같은 형식으로 만든 추정 주소라
      실패하거나 칸이 다를 수 있다. 실패한 줄은 그대로 복사해서 알려 주면 된다.
      이미 받은 파일은 건너뛴다. 다시 받으려면 파일을 지운다.
"""
import io
import os
import time

import pandas as pd
import requests

BASE = "https://baseballsavant.mlb.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (research script; contact: local)"}
OUT = "data/raw/seasons"
SEASONS = {"AAA": [2023, 2024, 2025, 2026],            # 트리플A 스탯캐스트는 2023년부터
           "MLB": list(range(2015, 2027))}              # MLB 스탯캐스트 지표는 2015년부터 (2026-11-15 확인: 2012년엔 구속·삼진·볼넷만)


def url(level, role, year):
    if level == "AAA":  # 01번에서 확인한 형식
        return (f"{BASE}/statcast-search-minors/csv?hfSea={year}%7C&hfLevel=AAA%7C&player_type={role}"
                "&group_by=name&min_pitches=100&minors=true")
    # MLB: 일반 스탯캐스트 검색의 같은 묶음 방식 (정규시즌만).
    # 2026-11-15 확인: type=details 를 붙이면 0행이 온다. 빼면 선수별 77칸이 온다.
    return (f"{BASE}/statcast_search/csv?hfSea={year}%7C&hfGT=R%7C&player_type={role}"
            "&group_by=name&min_pitches=100")


def main():
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


if __name__ == "__main__":
    main()
