"""전체 자료 파이프라인을 순서대로 실행한다 (제출·검수 때 처음부터 다시 만들어 볼 수 있도록).

실행:  python tools/run_all.py              전 단계 실행
       python tools/run_all.py --from 08    08번부터 실행
       python tools/run_all.py --only 08    08번만 실행 (화면 자료 docs/data.js 만 다시 만들 때)
       python tools/run_all.py --list       단계 목록만 보기

순서와 하는 일
  03  Baseball Savant 스탯캐스트 내려받기 + 2026 후보 풀 만들기      (data/candidates_2026.csv)
  05  MyKBO Stats KBO 외국인 성적 (2014~2026, 2010~2013 부분 명단) (data/kbo_foreign_seasons.csv)
  07  이름→선수 번호 연결 + MLB Stats API 시즌별 기록               (data/kbo_cohort.csv, data/raw/history_long.csv)
  09  MyKBO 선수 페이지에서 한국 등록명                             (data/kbo_korean_names.csv)
  10  연도·레벨별 리그 평균(환경 보정 기준)                          (data/league_rates.csv)
  11  기사에서 확인한 웨이버 공시·방출 사례                          (data/kbo_waivers.csv)
  12  MLB 투수 구종 사용 비율                                      (data/pitch_arsenal.csv)
  13  선수별 부상자 명단(IL) 이력                                   (data/il_stints.csv)
  08  위 자료를 합쳐 프로필·군집·검증을 계산하고 화면 자료를 만듦     (docs/data.js, 몇 분 걸림)

참고
- 인터넷 연결이 필요하다. 이미 받은 파일은 건너뛰므로 두 번째 실행부터는 빠르다. 처음 실행은 MyKBO 선수 페이지(약 300쪽, 6초 간격)
  때문에 30분 안팎, 체드윅 선수 명부(약 65MB) 다운로드가 포함된다. 원본은 data/raw/ 에 저장되며 git에는 올라가지 않는다.
- 각 단계는 "python -I"(외부 환경변수·현재 폴더 파이썬 파일을 읽지 않는 격리 모드)로 실행한다. 내려받은 자료를 읽는 스크립트이기 때문이다.
- 구버전 단계(01, 02, 04, 06)는 이 목록에 없다. 02번(체드윅 명부 내려받기)은 07번이 불러서 쓴다.
- 한 단계가 실패하면 거기서 멈추고 어느 단계인지 알려 준다.
"""
import argparse
import os
import subprocess
import sys
import time

STEPS = [
    ("03", "03_download_seasons.py", "스탯캐스트 내려받기 + 2026 후보 풀"),
    ("05", "05_kbo_seasons.py", "KBO 외국인 성적(MyKBO Stats)"),
    ("07", "07_fetch_history.py", "이름 연결 + 미국 시즌별 기록(MLB Stats API)"),
    ("09", "09_korean_names.py", "한국 등록명(MyKBO)"),
    ("10", "10_league_context.py", "리그 평균(환경 보정 기준)"),
    ("11", "11_waivers.py", "웨이버 공시·방출 사례(기사 확인분)"),
    ("12", "12_pitch_arsenal.py", "MLB 투수 구종 사용 비율"),
    ("13", "13_injuries.py", "부상자 명단 이력"),
    ("15", "15_careers.py", "경력·함께 뛴 사람 (docs/careers.js)"),
    ("08", "08_build_dataset.py", "프로필·군집·검증 계산 + docs/data.js"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", help="이 단계부터 실행 (예: 08)")
    ap.add_argument("--only", help="이 단계만 실행 (예: 08)")
    ap.add_argument("--list", action="store_true", help="단계 목록만 보기")
    a = ap.parse_args()
    ids = [s[0] for s in STEPS]
    for opt in (a.start, a.only):
        if opt and opt not in ids:
            sys.exit(f"알 수 없는 단계 '{opt}'. 가능한 값: {', '.join(ids)}")
    if a.list:
        for sid, f, desc in STEPS:
            print(f"{sid}  {f:28s} {desc}")
        return
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)  # 스크립트들이 data/, docs/ 를 저장소 최상위 기준으로 쓴다
    run = [s for s in STEPS if (a.only is None or s[0] == a.only)]
    if a.start:
        run = [s for s in run if ids.index(s[0]) >= ids.index(a.start)]
    t0 = time.time()
    for sid, f, desc in run:
        print(f"\n===== [{sid}] {desc} ({f}) =====", flush=True)
        t1 = time.time()
        r = subprocess.run([sys.executable, "-I", os.path.join("tools", f)])
        if r.returncode != 0:
            sys.exit(f"\n[{sid}] 단계가 실패했습니다(종료 코드 {r.returncode}). 위 메시지를 확인하세요.")
        print(f"----- [{sid}] 완료 ({time.time() - t1:.0f}초)", flush=True)
    print(f"\n전체 완료 ({time.time() - t0:.0f}초). 화면: docs/index.html")


if __name__ == "__main__":
    main()
