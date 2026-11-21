"""16단계: 마이너·MLB 팀 이름의 한글 발음 표(data/team_names_ko.csv)를 만든다. (History 의 팀 이름 마우스오버가 읽는다)

실행:  python -I tools/16_team_names_ko.py
입력:  docs/careers.js (15번이 만든 팀 이름 목록 T)
결과:  data/team_names_ko.csv   영문명, 한글 발음, 비고(멕시칸 리그 등)

방식: MLB 구단·멕시칸 리그 팀·특수 이름은 직접 적은 표를 쓰고, 나머지는 "도시 이름 + 별명" 표를 이어 붙인다.
      루키 리그(ACL/AZL/DSL/FCL/GCL/VSL) 팀은 "리그 이름 + 모구단 줄임말 + 색·번호"로 만든다.
      표에 없는 새 팀이 생기면 "못 만든 이름"으로 출력되니 아래 CITY·NICK·ORG 표에 한 줄 추가하고 다시 실행한다.
순서: 15번 → 16번 → 15번(한글 발음을 careers.js 에 넣는다)
"""
import csv, json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 팀 이름 목록(careers.js 의 T)
_js = open(os.path.join(ROOT, "docs", "careers.js"), encoding="utf-8").read()
names = json.loads(_js[_js.index("{"):_js.rindex("}") + 1])["T"]

MLB = {
    "Arizona Diamondbacks": "애리조나 다이아몬드백스", "Athletics": "애슬레틱스", "Atlanta Braves": "애틀랜타 브레이브스", "Baltimore Orioles": "볼티모어 오리올스",
    "Boston Red Sox": "보스턴 레드삭스", "Chicago Cubs": "시카고 컵스", "Chicago White Sox": "시카고 화이트삭스", "Cincinnati Reds": "신시내티 레즈",
    "Cleveland Guardians": "클리블랜드 가디언스", "Cleveland Indians": "클리블랜드 인디언스", "Colorado Rockies": "콜로라도 로키스", "Detroit Tigers": "디트로이트 타이거스",
    "Houston Astros": "휴스턴 애스트로스", "Kansas City Royals": "캔자스시티 로열스", "Los Angeles Angels": "로스앤젤레스 에인절스", "Los Angeles Dodgers": "로스앤젤레스 다저스",
    "Miami Marlins": "마이애미 말린스", "Milwaukee Brewers": "밀워키 브루어스", "Minnesota Twins": "미네소타 트윈스", "New York Mets": "뉴욕 메츠",
    "New York Yankees": "뉴욕 양키스", "Oakland Athletics": "오클랜드 애슬레틱스", "Philadelphia Phillies": "필라델피아 필리스", "Pittsburgh Pirates": "피츠버그 파이리츠",
    "San Diego Padres": "샌디에이고 파드리스", "San Francisco Giants": "샌프란시스코 자이언츠", "Seattle Mariners": "시애틀 매리너스", "St. Louis Cardinals": "세인트루이스 카디널스",
    "Tampa Bay Rays": "탬파베이 레이스", "Texas Rangers": "텍사스 레인저스", "Toronto Blue Jays": "토론토 블루제이스", "Washington Nationals": "워싱턴 내셔널스",
    "Florida Marlins": "플로리다 말린스", "Montreal Expos": "몬트리올 엑스포스", "Tampa Bay Devil Rays": "탬파베이 데블레이스",
}

MEX = {  # 멕시칸 리그(트리플A로 분류됨). 한글은 스페인어 발음
    "Acereros del Norte": "아세레로스 델 노르테", "Algodoneros Union Laguna": "알고도네로스 우니온 라구나", "Delfines de Ciudad del Carmen": "델피네스 데 시우다드 델 카르멘",
    "Diablos Rojos del Mexico": "디아블로스 로호스 델 멕시코", "Generales de Durango": "헤네랄레스 데 두랑고", "Guerreros de Oaxaca": "게레로스 데 오악사카",
    "Leones de Yucatan": "레오네스 데 유카탄", "Pericos de Puebla": "페리코스 데 푸에블라", "Piratas de Campeche": "피라타스 데 캄페체",
    "Rieleros de Aguascalientes": "리엘레로스 데 아과스칼리엔테스", "Rojos del Aguila de Veracruz": "로호스 델 아길라 데 베라크루스", "Saraperos de Saltillo": "사라페로스 데 살티요",
    "Sultanes de Monterrey": "술타네스 데 몬테레이", "Tigres de Quintana Roo": "티그레스 데 킨타나로오", "Toros de Tijuana": "토로스 데 티후아나", "Vaqueros de la Laguna": "바케로스 데 라 라구나",
}

SPECIAL = {
    "Office of the Commissioner": "커미셔너 사무국", "Swing of the Quad Cities": "스윙 오브 더 쿼드시티스", "Oklahoma City Baseball Club": "오클라호마시티 베이스볼 클럽",
    "Scranton/Wilkes-Barre RailRiders": "스크랜턴/윌크스배리 레일라이더스", "Scranton/Wilkes-Barre Yankees": "스크랜턴/윌크스배리 양키스",
}

CITY = {
    # 트리플A
    "Albuquerque": "앨버커키", "Buffalo": "버펄로", "Charlotte": "샬럿", "Colorado Springs": "콜로라도스프링스", "Columbus": "콜럼버스", "Durham": "더럼", "El Paso": "엘패소",
    "Fresno": "프레즈노", "Gwinnett": "귀닛", "Indianapolis": "인디애나폴리스", "Iowa": "아이오와", "Jacksonville": "잭슨빌", "Las Vegas": "라스베이거스",
    "Lehigh Valley": "리하이밸리", "Louisville": "루이빌", "Memphis": "멤피스", "Nashville": "내슈빌", "New Orleans": "뉴올리언스", "Norfolk": "노퍽",
    "Oklahoma City": "오클라호마시티", "Omaha": "오마하", "Pawtucket": "포터킷", "Reno": "리노", "Richmond": "리치먼드", "Rochester": "로체스터", "Round Rock": "라운드록",
    "Sacramento": "새크라멘토", "Salt Lake": "솔트레이크", "San Antonio": "샌안토니오", "St. Paul": "세인트폴", "Sugar Land": "슈거랜드", "Syracuse": "시러큐스",
    "Tacoma": "타코마", "Toledo": "톨리도", "Tucson": "투손", "Worcester": "우스터",
    # 더블A
    "Akron": "애크런", "Altoona": "앨투나", "Amarillo": "애머릴로", "Arkansas": "아칸소", "Biloxi": "빌럭시", "Binghamton": "빙엄턴", "Birmingham": "버밍햄", "Bowie": "보위",
    "Carolina": "캐롤라이나", "Chattanooga": "채터누가", "Chesapeake": "체서피크", "Corpus Christi": "코퍼스크리스티", "Erie": "이리", "Frisco": "프리스코", "Greenville": "그린빌",
    "Harrisburg": "해리스버그", "Hartford": "하트퍼드", "Huntsville": "헌츠빌", "Jackson": "잭슨", "Knoxville": "녹스빌", "Midland": "미들랜드", "Mississippi": "미시시피",
    "Mobile": "모바일", "Montgomery": "몽고메리", "New Britain": "뉴브리튼", "New Hampshire": "뉴햄프셔", "Northwest Arkansas": "노스웨스트아칸소", "Pensacola": "펜서콜라",
    "Portland": "포틀랜드", "Reading": "레딩", "Rocket City": "로켓시티", "Somerset": "서머싯", "Springfield": "스프링필드", "Tennessee": "테네시", "Trenton": "트렌턴",
    "Tulsa": "털사", "West Tenn": "웨스트테네시", "Wichita": "위치타",
    # 하이A
    "Aberdeen": "애버딘", "Asheville": "애슈빌", "Bakersfield": "베이커즈필드", "Beloit": "벨로이트", "Bowling Green": "볼링그린", "Bradenton": "브레이든턴",
    "Brevard County": "브레바드카운티", "Brooklyn": "브루클린", "Buies Creek": "바이스크리크", "Cedar Rapids": "시더래피즈", "Clearwater": "클리어워터", "Dayton": "데이턴",
    "Daytona": "데이토나", "Down East": "다운이스트", "Dunedin": "더니든", "Eugene": "유진", "Everett": "에버렛", "Fayetteville": "페이엇빌", "Florida": "플로리다",
    "Fort Myers": "포트마이어스", "Fort Wayne": "포트웨인", "Frederick": "프레더릭", "Great Lakes": "그레이트레이크스", "Greensboro": "그린즈버러", "Hickory": "히커리",
    "High Desert": "하이데저트", "Hillsboro": "힐즈버러", "Hub City": "허브시티", "Hudson Valley": "허드슨밸리", "Inland Empire": "인랜드엠파이어", "Jersey Shore": "저지쇼어",
    "Jupiter": "주피터", "Kinston": "킨스턴", "Lake County": "레이크카운티", "Lake Elsinore": "레이크엘시노어", "Lakeland": "레이클랜드", "Lancaster": "랭커스터", "Lansing": "랜싱",
    "Lynchburg": "린치버그", "Modesto": "모데스토", "Myrtle Beach": "머틀비치", "Palm Beach": "팜비치", "Peoria": "피오리아", "Potomac": "포토맥", "Quad Cities": "쿼드시티스",
    "Rancho Cucamonga": "랜초쿠카몽가", "Rome": "롬", "Salem": "세일럼", "San Jose": "새너제이", "Sarasota": "새러소타", "South Bend": "사우스벤드", "Spokane": "스포캔",
    "St. Lucie": "세인트루시", "Stockton": "스톡턴", "Tampa": "탬파", "Tri-City": "트라이시티", "Vancouver": "밴쿠버", "Vero Beach": "비로비치", "Visalia": "비살리아",
    "West Michigan": "웨스트미시간", "Wilmington": "윌밍턴", "Winston-Salem": "윈스턴세일럼", "Wisconsin": "위스콘신",
    # A / 숏A
    "Augusta": "오거스타", "Burlington": "벌링턴", "Charleston": "찰스턴", "Clinton": "클린턴", "Columbia": "컬럼비아", "Delmarva": "델마바", "Fredericksburg": "프레더릭스버그",
    "Hagerstown": "헤이거스타운", "Kane County": "케인카운티", "Kannapolis": "캐내폴리스", "Lakewood": "레이크우드", "Lexington": "렉싱턴", "Macon": "메이컨", "Ontario": "온타리오",
    "Savannah": "서배너", "West Virginia": "웨스트버지니아", "Auburn": "오번", "Batavia": "바타비아", "Boise": "보이시", "Connecticut": "코네티컷", "Jamestown": "제임스타운",
    "Lowell": "로웰", "Mahoning Valley": "마호닝밸리", "Oneonta": "오니온타", "Salem-Keizer": "세일럼-카이저", "State College": "스테이트칼리지", "Staten Island": "스태튼아일랜드",
    "Vermont": "버몬트", "Williamsport": "윌리엄스포트", "Yakima": "야키마",
    # 루키
    "Billings": "빌링스", "Bluefield": "블루필드", "Bristol": "브리스톨", "Casper": "캐스퍼", "Danville": "댄빌", "Elizabethton": "엘리자베스턴", "Grand Junction": "그랜드정션",
    "Great Falls": "그레이트폴스", "Greeneville": "그린빌", "Helena": "헬레나", "Idaho Falls": "아이다호폴스", "Johnson City": "존슨시티", "Kingsport": "킹스포트", "Missoula": "미줄라",
    "Ogden": "오그던", "Orem": "오럼", "Princeton": "프린스턴", "Pulaski": "풀래스키",
}

NICK = {
    "Isotopes": "아이소토프스", "Bisons": "바이슨스", "Knights": "나이츠", "Sky Sox": "스카이삭스", "Clippers": "클리퍼스", "Bulls": "불스", "Chihuahuas": "치와와스",
    "Grizzlies": "그리즐리스", "Braves": "브레이브스", "Stripers": "스트라이퍼스", "Indians": "인디언스", "Cubs": "컵스", "Jumbo Shrimp": "점보 슈림프", "51s": "51스",
    "Aviators": "에이비에이터스", "IronPigs": "아이언피그스", "Bats": "뱃츠", "Redbirds": "레드버즈", "Sounds": "사운즈", "Baby Cakes": "베이비케이크스", "Zephyrs": "제퍼스",
    "Tides": "타이즈", "Comets": "코미츠", "Dodgers": "다저스", "RedHawks": "레드호크스", "Royals": "로열스", "Storm Chasers": "스톰체이서스", "Red Sox": "레드삭스", "Aces": "에이시스",
    "Red Wings": "레드윙스", "Express": "익스프레스", "River Cats": "리버캣츠", "Bees": "비스", "Missions": "미션스", "RailRiders": "레일라이더스", "Yankees": "양키스", "Saints": "세인츠",
    "Skeeters": "스키터스", "Space Cowboys": "스페이스 카우보이스", "Chiefs": "치프스", "Mets": "메츠", "Rainiers": "레이니어스", "Mud Hens": "머드헨스", "Padres": "파드리스",
    "Sidewinders": "사이드와인더스", "Aeros": "에어로스", "RubberDucks": "러버덕스", "Curve": "커브", "Sod Poodles": "소드 푸들스", "Travelers": "트래블러스", "Shuckers": "셔커스",
    "Rumble Ponies": "럼블 포니스", "Barons": "배런스", "Baysox": "베이삭스", "Mudcats": "머드캣츠", "Lookouts": "룩아웃츠", "Clingstones": "클링스톤스", "Hooks": "훅스",
    "SeaWolves": "시울브스", "RoughRiders": "러프라이더스", "Senators": "세네터스", "Yard Goats": "야드 고츠", "Stars": "스타스", "Generals": "제너럴스", "Suns": "선스",
    "Smokies": "스모키스", "RockHounds": "락하운즈", "BayBears": "베이베어스", "Biscuits": "비스킷츠", "Rock Cats": "락 캣츠", "Fisher Cats": "피셔 캣츠", "Naturals": "내추럴스",
    "Blue Wahoos": "블루 와후스", "Sea Dogs": "시 독스", "Fightin Phils": "파이팅 필스", "Phillies": "필리스", "Flying Squirrels": "플라잉 스쿼럴스", "Trash Pandas": "트래시 팬더스",
    "Patriots": "패트리어츠", "Cardinals": "카디널스", "Thunder": "선더", "Drillers": "드릴러스", "Diamond Jaxx": "다이아몬드 잭스", "Wind Surge": "윈드 서지",
    "IronBirds": "아이언버즈", "Tourists": "투어리스츠", "Blaze": "블레이즈", "Sky Carp": "스카이 카프", "Snappers": "스내퍼스", "Hot Rods": "핫 로즈", "Marauders": "마라우더스",
    "Manatees": "매너티스", "Cyclones": "사이클론스", "Astros": "애스트로스", "Kernels": "커널스", "Stone Crabs": "스톤 크랩스", "Threshers": "쓰레셔스", "Dragons": "드래곤스",
    "Tortugas": "토르투가스", "Wood Ducks": "우드 덕스", "Blue Jays": "블루제이스", "Emeralds": "에메랄즈", "AquaSox": "아쿠아삭스", "Woodpeckers": "우드페커스",
    "Fire Frogs": "파이어 프로그스", "Miracle": "미라클", "TinCaps": "틴캡스", "Keys": "키스", "Loons": "룬스", "Grasshoppers": "그래스호퍼스", "Drive": "드라이브",
    "Crawdads": "크로대즈", "Mavericks": "매버릭스", "Hops": "홉스", "Spartanburgers": "스파턴버거스", "Renegades": "레니게이즈", "66ers": "66어스", "BlueClaws": "블루클로스",
    "Hammerheads": "해머헤즈", "Captains": "캡틴스", "Storm": "스톰", "Flying Tigers": "플라잉 타이거스", "Tigers": "타이거스", "JetHawks": "제트호크스", "Lugnuts": "러그너츠",
    "Hillcats": "힐캣츠", "Nuts": "너츠", "Pelicans": "펠리컨스", "Nationals": "내셔널스", "River Bandits": "리버 밴디츠", "Quakes": "퀘이크스", "Emperors": "엠퍼러스",
    "Giants": "자이언츠", "Reds": "레즈", "Silver Hawks": "실버 호크스", "Ports": "포츠", "Tarpons": "타폰스", "Dust Devils": "더스트 데블스", "Canadians": "캐네디언스",
    "Oaks": "오크스", "Rawhide": "로하이드", "Whitecaps": "화이트캡스", "Blue Rocks": "블루 락스", "Dash": "대시", "Warthogs": "워트호그스", "Timber Rattlers": "팀버 래틀러스",
    "GreenJackets": "그린재킷츠", "RiverDogs": "리버독스", "LumberKings": "럼버킹스", "Fireflies": "파이어플라이스", "Shorebirds": "쇼어버즈", "Mighty Mussels": "마이티 머슬스",
    "Cougars": "쿠거스", "Cannon Ballers": "캐넌 볼러스", "Intimidators": "인티미데이터스", "Legends": "레전즈", "Tower Buzzers": "타워 버저스", "Sand Gnats": "샌드 냇츠",
    "Power": "파워", "Doubledays": "더블데이스", "Muckdogs": "머크독스", "Hawks": "호크스", "Jammers": "재머스", "Spinners": "스피너스", "Scrappers": "스크래퍼스",
    "Volcanoes": "볼케이노스", "Spikes": "스파이크스", "ValleyCats": "밸리캣츠", "Lake Monsters": "레이크 몬스터스", "Black Bears": "블랙 베어스", "Crosscutters": "크로스커터스",
    "Bears": "베어스", "Mustangs": "머스탱스", "Blue Jays": "블루제이스", "Pirates": "파이리츠", "White Sox": "화이트삭스", "Ghosts": "고스츠", "Rockies": "로키스",
    "Twins": "트윈스", "Voyagers": "보이저스", "Chukars": "처커스", "Osprey": "오스프리", "Raptors": "랩터스", "Owlz": "아울스", "Devil Rays": "데블레이스", "Rays": "레이스",
    "Mariners": "매리너스", "Brewers": "브루어스",
}

ORG = {  # 루키 리그(ACL/AZL/DSL/FCL/GCL/VSL) 팀의 모구단 줄임말
    "Angels": "에인절스", "Athletics": "애슬레틱스", "Astros": "애스트로스", "Blue Jays": "블루제이스", "Braves": "브레이브스", "Brewers": "브루어스", "Cardinals": "카디널스",
    "Cubs": "컵스", "D-backs": "다이아몬드백스", "Diamondbacks": "다이아몬드백스", "Dodgers": "다저스", "Giants": "자이언츠", "Guardians": "가디언스", "Indians": "인디언스",
    "Mariners": "매리너스", "Marlins": "말린스", "Mets": "메츠", "Nationals": "내셔널스", "Orioles": "오리올스", "Padres": "파드리스", "Phillies": "필리스", "Pirates": "파이리츠",
    "Rangers": "레인저스", "Rays": "레이스", "Reds": "레즈", "Red Sox": "레드삭스", "Rockies": "로키스", "Royals": "로열스", "Tigers": "타이거스", "Twins": "트윈스",
    "White Sox": "화이트삭스", "Yankees": "양키스", "Expos": "엑스포스", "Devil Rays": "데블레이스", "Colorado": "콜로라도", "Indians/Brewers": "인디언스/브루어스",
    "Devil Rays/Reds": "데블레이스/레즈", "Red Sox/Padres": "레드삭스/파드리스",
    "BOS": "보스턴", "LAD": "LA 다저스", "NYY": "뉴욕 양키스", "PIT": "피츠버그", "TEX": "텍사스", "NYY Yankees": "뉴욕 양키스",
}
LEAGUE = {"ACL": "애리조나 컴플렉스리그", "AZL": "애리조나 컴플렉스리그", "DSL": "도미니칸 서머리그", "FCL": "플로리다 컴플렉스리그", "GCL": "걸프코스트리그", "VSL": "베네수엘라 서머리그"}
SUFFIX = {"Blue": "블루", "Red": "레드", "Gold": "골드", "Orange": "오렌지", "Black": "블랙", "Green": "그린", "White": "화이트", "East": "이스트", "West": "웨스트",
          "Lasorda": "라소다", "Mota": "모타", "Guerrero": "게레로", "Robinson": "로빈슨", "Shoemaker": "슈메이커", "Bautista": "바우티스타", "Mega": "메가",
          "1": "1", "2": "2"}


def rookie(n):
    m = re.match(r"^(ACL|AZL|DSL|FCL|GCL|VSL) (.+)$", n)
    if not m:
        return None
    lg, rest = m.group(1), m.group(2)
    if rest in ORG:
        return f"{LEAGUE[lg]} {ORG[rest]}"
    # 마지막 단어가 색·번호·이름이면 떼어 낸다 (예: "Astros Blue", "Cubs 1", "Dodgers Lasorda", "LAD Bautista", "Yankees1")
    mm = re.match(r"^(.*?)\s*([A-Za-z]+|\d)$", rest)
    for base, suf in ((rest.rsplit(" ", 1) + [""])[:2], ):
        pass
    parts = rest.rsplit(" ", 1)
    if len(parts) == 2 and parts[0] in ORG and parts[1] in SUFFIX:
        return f"{LEAGUE[lg]} {ORG[parts[0]]} {SUFFIX[parts[1]]}"
    m2 = re.match(r"^(.+?)(\d)$", rest)           # "Yankees1" 처럼 붙은 번호
    if m2 and m2.group(1) in ORG:
        return f"{LEAGUE[lg]} {ORG[m2.group(1)]} {m2.group(2)}"
    return None


def compose(n):
    if n in MLB:
        return MLB[n], ""
    if n in MEX:
        return MEX[n], "멕시칸 리그"
    if n in SPECIAL:
        return SPECIAL[n], ""
    r = rookie(n)
    if r:
        return r, ""
    for city in sorted(CITY, key=len, reverse=True):          # 긴 도시 이름부터
        if n.startswith(city + " "):
            nick = n[len(city) + 1:]
            if nick in NICK:
                return f"{CITY[city]} {NICK[nick]}", ""
    return None, ""


rows, miss = [], []
for n in names:
    if not isinstance(n, str) or not n or n == "NaN" or n is None:
        continue
    ko, note = compose(n)
    if ko is None:
        miss.append(n)
    else:
        rows.append((n, ko, note))
print("전체", len(names), "| 만든 것", len(rows), "| 못 만든 것", len(miss))
print("못 만든 이름:", miss)
out = ROOT + r"\data\team_names_ko.csv"
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["영문명", "한글 발음", "비고"])
    for r in sorted(rows):
        w.writerow(r)
print("saved", out)
