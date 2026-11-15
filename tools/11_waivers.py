"""11단계: 웨이버 공시·방출 사례를 선수 명단과 맞춰 data/kbo_waivers.csv 로 만든다.

실행:  python -I tools/11_waivers.py
결과:  data/kbo_waivers.csv   (mykbo_id, 영문명, 한국등록명, 구분, 일자, 일자정확도, 당시구단, 출처, 비고)

자료 출처: 아래 CASES 는 뉴스 기사를 읽고 직접 옮겨 적은 것이다(2026-11-15). 각 줄에 기사 주소를 적었다.
  KBO 공식 사이트(선수 이동 현황)에 전체 목록이 있지만 자동 수집이 금지되어 있어 쓰지 않았다.
  MyKBO Stats 선수 페이지에는 웨이버·방출 정보가 없다(294쪽 확인).

중요한 한계
- 이 목록은 **전체가 아니다.** 검색으로 찾아 기사를 읽고 확인한 사례만 있다. 목록에 없다고 해서 공시되지 않았다는 뜻이 아니다.
- 구분: "웨이버 공시" = 기사 본문에 웨이버 공시가 나온 경우. "방출·퇴출(웨이버 명시 없음)" = 기사에 방출·퇴출만 나온 경우.
- 일자정확도: "확인" = 기사에서 연·월·일을 확인, "월 단위" = 월까지만, "다른 기사 기준" = 일자를 다른 기사 문장으로 계산.
- 같은 선수의 여러 사건은 줄을 나눠 적는다.
"""
import sys
import unicodedata
import re

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# last: 영문 성(악센트 무시, 소문자), year: MyKBO 기준 KBO 첫해(여러 명이면 구분용, 없으면 None)
CASES = [
    dict(last="florial", year=2025, kind="웨이버 공시", date="2025-07-19", acc="확인", team="한화",
         src="https://osen.co.kr/article/G1112616629", note="대체 외국인 리베라토와 정식 계약"),
    dict(last="barnes", first="charlie", year=None, kind="웨이버 공시", date="2025-05-13", acc="확인", team="롯데",
         src="https://sports.khan.co.kr/article/202505131755003", note="KBO가 롯데의 요청을 수용해 공시"),
    dict(last="wiles", year=2026, kind="웨이버 공시", date="2026-06-29", acc="확인", team="키움",
         src="https://sports.khan.co.kr/article/202606291130003", note="공시 요청일. 기사는 소속을 명시하지 않아 키움으로 보임"),
    dict(last="davidson", year=2024, kind="웨이버 공시", date="2026-06-27", acc="확인", team="NC",
         src="https://sports.khan.co.kr/article/202606291130003", note="2026시즌. 이후 키움이 계약 양도 신청"),
    dict(last="kingham", year=2020, kind="웨이버 공시", date="2022-06-02", acc="확인", team="한화",
         src="https://isplus.com/article/view/isp202206020260", note="공시 요청일"),
    dict(last="kingham", year=2020, kind="웨이버 공시", date="2020-07-02", acc="다른 기사 기준", team="SK",
         src="https://isplus.com/article/view/isp202206020260", note="2022년 기사가 '2020년 7월 2일 웨이버 공시된 이력'을 언급. 원 기사는 확인하지 않음"),
    dict(last="carpenter", year=2022, kind="웨이버 공시", date="2022-05-31", acc="확인", team="한화",
         src="https://isplus.com/article/view/isp202206020260", note="기사에 '지난 5월 31일'로 언급"),
    dict(last="mackinnon", year=2024, kind="웨이버 공시", date="2024-07-09", acc="확인", team="삼성",
         src="https://osen.co.kr/article/G1112373239", note="삼성이 9일 KBO에 신청, KBO가 공시"),
    dict(last="dale", year=2026, kind="웨이버 공시", date="2026-05-26", acc="확인", team="KIA",
         src="https://www.starnewskorea.com/sports/2026/05/27/2026052616141199263", note="아시아쿼터 내야수, 신청일"),
    dict(last="alcantara", year=None, kind="웨이버 공시", date="2024-07-04", acc="다른 기사 기준", team="두산",
         src="https://isplus.com/article/view/isp202407080125", note="웨이버 공시 사실은 이 기사, 일자('지난 4일')는 https://osen.co.kr/article/G1112373239 기준"),
    dict(last="dugger", year=2024, kind="방출·퇴출(웨이버 명시 없음)", date="2024-04", acc="월 단위", team="SSG",
         src="https://osen.co.kr/article/G1112373239", note="2024년 4월말 방출(정확한 일자 확인 못 함)"),
    dict(last="pena", year=None, kind="방출·퇴출(웨이버 명시 없음)", date="2024-05", acc="월 단위", team="한화",
         src="https://osen.co.kr/article/G1112373239", note="2024년 5월말 퇴출(정확한 일자 확인 못 함)"),
    dict(last="cuevas", year=None, kind="방출·퇴출(웨이버 명시 없음)", date="2022-05", acc="월 단위", team="KT",
         src="https://isplus.com/article/view/isp202205180077", note="기사 등록일 2022-05-18, 대체 선수 벤자민 영입 발표. 웨이버 일자는 본문에 없음"),
]


def norm(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z ]", " ", s.lower()).split()


def main():
    co = pd.read_csv("data/kbo_cohort.csv", dtype=str).fillna("")
    kn = pd.read_csv("data/kbo_korean_names.csv", dtype=str).fillna("").set_index("mykbo_id")["한국등록명"].to_dict()
    # MyKBO 전체 선수(2014~)에서 찾기 위해 연도별 목록도 쓴다 (첫해 선수가 아니어도 웨이버 사건은 있을 수 있음)
    allp = pd.read_csv("data/kbo_foreign_seasons.csv", dtype=str).fillna("")[["mykbo_id", "영문명"]].drop_duplicates()
    rows, miss = [], []
    for c in CASES:
        hit = allp[allp["영문명"].map(lambda n: c["last"] in norm(n))]
        if c.get("first"):
            hit = hit[hit["영문명"].map(lambda n: c["first"] in norm(n))]
        if c["year"] is not None:
            ids = set(co[(co["KBO첫해"] == str(c["year"]))]["mykbo_id"])
            sub = hit[hit["mykbo_id"].isin(ids)]
            hit = sub if len(sub) else hit
        if len(hit) != 1:
            miss.append((c["last"], c["date"], len(hit), hit["영문명"].tolist()[:4]))
            continue
        pid = hit.iloc[0]["mykbo_id"]
        in_cohort = pid in set(co["mykbo_id"])
        rows.append({"mykbo_id": pid, "영문명": hit.iloc[0]["영문명"], "한국등록명": kn.get(pid, ""), "구분": c["kind"], "일자": c["date"],
                     "일자정확도": c["acc"], "당시구단": c["team"], "출처": c["src"], "비고": c["note"], "지난사례포함": "예" if in_cohort else "아니오"})
    df = pd.DataFrame(rows).sort_values("일자")
    df.to_csv("data/kbo_waivers.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220, "display.unicode.east_asian_width", True)
    print(df[["영문명", "한국등록명", "구분", "일자", "일자정확도", "당시구단", "지난사례포함"]].to_string(index=False))
    print("\n연결 못 함(0명 또는 여러 명):", miss)


if __name__ == "__main__":
    main()
