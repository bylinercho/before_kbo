"""12단계: MLB 투수의 구종별 사용 비율을 Baseball Savant 구종 리더보드에서 받는다.

실행:  python -I tools/12_pitch_arsenal.py
결과:  data/raw/arsenal/<연도>.csv   받은 원본 (git 제외)
       data/pitch_arsenal.csv          투수·연도별 구종 사용 비율(%) (n_ff 포심, n_si 싱커, n_fc 커터, n_sl 슬라이더,
                                       n_ch 체인지업, n_cu 커브, n_fs 스플리터, n_kn 너클볼, n_st 스위퍼, n_sv 슬러브)

한계 (2026-11-15 확인)
- MLB 투수만 나온다. 트리플A 스탯캐스트 검색은 구종별로 묶이지 않아(group_by=name-pitch_type 이 무시됨) 마이너 구종 자료가 없다.
- 리더보드는 최소 투구 수 100개(min=100)인 투수만 담는다.

규칙: 요청 사이 5초 쉰다. 이미 받은 연도는 다시 받지 않는다.
"""
import io
import os
import sys
import time

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

OUT = "data/raw/arsenal"
H = {"User-Agent": "Mozilla/5.0 (research script)"}
URL = "https://baseballsavant.mlb.com/leaderboard/pitch-arsenals?year={y}&min=100&type=n_&hand=&csv=true"


def main():
    os.makedirs(OUT, exist_ok=True)
    frames = []
    for y in range(2015, 2027):
        path = os.path.join(OUT, f"{y}.csv")
        if not os.path.exists(path):
            try:
                r = requests.get(URL.format(y=y), headers=H, timeout=120)
                r.raise_for_status()
                d = pd.read_csv(io.StringIO(r.text))
                if len(d) == 0:
                    raise ValueError("0행")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(r.text)
            except Exception as e:
                print(y, "실패", repr(e)[:100], flush=True)
                time.sleep(5)
                continue
            time.sleep(5)
        d = pd.read_csv(path, encoding="utf-8")
        d["year"] = y
        d = d.rename(columns={"pitcher": "player_id"})
        frames.append(d)
        print(y, len(d), "명", flush=True)
    df = pd.concat(frames, ignore_index=True)
    cols = ["player_id", "year"] + [c for c in df.columns if c.startswith("n_")]
    df[cols].to_csv("data/pitch_arsenal.csv", index=False, encoding="utf-8-sig")
    print("저장:", len(df), "줄 /", df["player_id"].nunique(), "명")


if __name__ == "__main__":
    main()
