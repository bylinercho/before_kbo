"""1단계: 스탯캐스트에서 데이터를 받을 수 있는지, 어떤 칸이 들어 있는지 확인한다.

실행:  pip install requests pandas
       python tools/01_check_statcast.py

결과: data/raw/ 폴더에 CSV 3개가 저장되고, 각 파일의 행 수와 칸 이름이 화면에 나온다.
      그 화면 내용을 그대로 복사해서 알려 주면 다음 단계를 정할 수 있다.

주의: 이 스크립트는 작성자가 직접 실행해 보지 못했다(작성 환경에서 해당 사이트 접속이 막혀 있음).
      ① 주소는 내용이 내려오는 것을 확인했고, ②③ 주소는 파일이 내려오는 것까지만 확인했다.
      칸 이름과 내용은 이 스크립트로 처음 확인하는 것이다.
"""
import io
import os
import time

import pandas as pd
import requests

BASE = "https://baseballsavant.mlb.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (research script; contact: local)"}

TARGETS = {
    # ① 메이저리그 2026 타자 배트 추적 (배트 속도, 스윙 길이, 정타 비율 등)
    "mlb_bat_tracking_2026.csv":
        f"{BASE}/leaderboard/bat-tracking?seasonStart=2026&seasonEnd=2026&type=batter&minSwings=q&csv=true",
    # ② 트리플A 2026 투수: 선수별로 묶은 값
    "aaa_pitchers_2026.csv":
        f"{BASE}/statcast-search-minors/csv?hfSea=2026%7C&hfLevel=AAA%7C&player_type=pitcher"
        "&group_by=name&min_pitches=500&minors=true",
    # ③ 트리플A 2026 타자: 선수별로 묶은 값
    "aaa_batters_2026.csv":
        f"{BASE}/statcast-search-minors/csv?hfSea=2026%7C&hfLevel=AAA%7C&player_type=batter"
        "&group_by=name&min_pitches=500&minors=true",
}


def main():
    os.makedirs("data/raw", exist_ok=True)
    for name, url in TARGETS.items():
        print("=" * 70)
        print(name)
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            print("  응답 코드:", r.status_code, "/ 크기:", len(r.content), "바이트")
            r.raise_for_status()
            with open(os.path.join("data/raw", name), "wb") as f:
                f.write(r.content)
            df = pd.read_csv(io.BytesIO(r.content))
            print("  행 수:", len(df), "/ 칸 수:", len(df.columns))
            print("  칸 이름:", list(df.columns))
            print(df.head(3).to_string())
        except Exception as e:  # 어떤 오류든 그대로 보여 주고 다음 파일로 넘어간다
            print("  실패:", repr(e))
        time.sleep(5)  # 사이트에 부담을 주지 않도록 요청 사이에 쉰다


if __name__ == "__main__":
    main()
