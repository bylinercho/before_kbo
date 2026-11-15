"""9단계: 지난 사례(KBO 첫해 외국인)의 한국 등록명을 MyKBO Stats 선수 페이지에서 받는다.

실행:  python -I tools/09_korean_names.py
입력:  data/kbo_cohort.csv (07번)
결과:  data/raw/mykbo/players/<id>.html   받은 원본 (git 제외)
       data/kbo_korean_names.csv           mykbo_id, 영문명, 한국등록명, 비고

출처: https://mykbostats.com/players/<id> 의 itemprop="alternateName" 항목 (예: Yonny Chirinos → 치리노스).
      KBO 공식 등록명과 표기가 같다고 확인한 것은 아니다(MyKBO 표기). 비어 있으면 그 페이지에 한글 이름이 없는 것이다.

규칙: robots.txt가 요청 간격 5초(Crawl-delay)를 요구해 6초씩 쉰다. 선수당 1쪽만 받고, 이미 받은 쪽은 다시 받지 않는다.
      (약관: 자동 도구 사용 허용, 과도한 요청 금지. 2026-11-15 확인)
"""
import html
import os
import re
import sys
import time

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")

OUT = "data/raw/mykbo/players"
HEADERS = {"User-Agent": "Mozilla/5.0 (research script)"}


def parse(page):
    m = re.search(r'itemprop="alternateName"[^>]*>\s*([^<]+?)\s*<', page)
    return html.unescape(m.group(1)).strip() if m else ""


def main():
    os.makedirs(OUT, exist_ok=True)
    co = pd.read_csv("data/kbo_cohort.csv", dtype=str).fillna("")
    rows, fetched = [], 0
    for i, r in enumerate(co.itertuples(index=False), 1):
        path = os.path.join(OUT, f"{r.mykbo_id}.html")
        note = ""
        if os.path.exists(path):
            page = open(path, encoding="utf-8").read()
        else:
            try:
                resp = requests.get(f"https://mykbostats.com/players/{r.mykbo_id}", headers=HEADERS, timeout=60)
                resp.raise_for_status()
                resp.encoding = "utf-8"
                page = resp.text
                with open(path, "w", encoding="utf-8") as f:
                    f.write(page)
                fetched += 1
            except Exception as e:
                page, note = "", f"받기 실패: {repr(e)[:80]}"
            time.sleep(6)
        ko = parse(page) if page else ""
        if page and not ko:
            note = "페이지에 한글 이름 없음"
        rows.append({"mykbo_id": r.mykbo_id, "영문명": r.영문명, "한국등록명": ko, "비고": note})
        if i % 20 == 0 or i == len(co):
            print(f"{i}/{len(co)}명 처리 (새로 받은 쪽 {fetched})", flush=True)
            pd.DataFrame(rows).to_csv("data/kbo_korean_names.csv", index=False, encoding="utf-8-sig")
    df = pd.DataFrame(rows)
    df.to_csv("data/kbo_korean_names.csv", index=False, encoding="utf-8-sig")
    print("=" * 70)
    print("한국 등록명 있음:", int((df["한국등록명"] != "").sum()), "/", len(df))
    print(df["비고"].value_counts().to_string())


if __name__ == "__main__":
    main()
