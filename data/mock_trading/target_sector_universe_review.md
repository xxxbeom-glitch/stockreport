# 산업 종목풀 검토 리포트 (사업 근거 기반)

- 생성 시각: 2026-05-22T19:40:01+09:00
- 분류 방식: business_evidence_based
- 기준일: 20260522

## 데이터 소스
- pykrx_kosdaq_list: 사용
- pykrx_krx_industry: 사용
- kr_watchlist_verified: 사용
- naver_coinfo_business: 사용
- kis_price_filter_applied: 미사용/부족
- dart_company_profile: 미사용/부족
- naver_news_primary: 미사용/부족

## 산업군별 포함 종목 수

| 산업군 | 포함(included) | 검토필요(needs_review) |
|--------|----------------|------------------------|
| AI 반도체 소재·부품·장비 | 215 | 92 |
| 전력기술 | 42 | 6 |
| 산업·로봇 장비 | 74 | 45 |

## 기존 키워드 79종 대비

- 종목명 키워드 매칭(가격 무관): **83**종
- 그중 사업 근거 부족으로 **제외·재검토**: **5**종
- 사업 근거 **included** 합계: **323**종
- 키워드로는 놓쳤으나 사업 설명으로 **포함 확인**: **30**종

  - HPSP / 403870 → ai_semiconductor_material_equipment
  - 하나마이크론 / 067310 → ai_semiconductor_material_equipment
  - 피에스케이 / 319660 → ai_semiconductor_material_equipment
  - 원익QnC / 074600 → ai_semiconductor_material_equipment
  - 디아이 / 003160 → ai_semiconductor_material_equipment
  - 엘오티베큠 / 083310 → ai_semiconductor_material_equipment
  - 케이씨텍 / 281820 → ai_semiconductor_material_equipment
  - 오로스테크놀로지 / 322310 → ai_semiconductor_material_equipment
  - 에프에스티 / 036810 → ai_semiconductor_material_equipment
  - 동진쎄미켐 / 005290 → ai_semiconductor_material_equipment
  - 원익머트리얼즈 / 104830 → ai_semiconductor_material_equipment
  - 비에이치 / 090460 → ai_semiconductor_material_equipment
  - 테크윙 / 089030 → ai_semiconductor_material_equipment
  - 에스티아이 / 039440 → ai_semiconductor_material_equipment
  - 에스피지 / 058610 → industrial_robot_equipment

## 필수 검토 6종목

| 종목 | 코드 | 산업군 | 검토상태 | 신뢰도 | 사업 요약 |
|------|------|--------|----------|--------|-----------|
| 에스피지 | 058610 | industrial_robot_equipment | included | high | 정밀 제어용 모터·감속기 |
| 원익QnC | 074600 | ai_semiconductor_material_equipment | included | high | 식각 공정용 쿼츠웨어 제조 |
| 하나마이크론 | 067310 | ai_semiconductor_material_equipment | included | high | 어드밴스드 패키징 및 테스트 |
| 피에스케이 | 319660 | ai_semiconductor_material_equipment | included | high | 전공정 PR 스트립(감광액 제거) 장비 |
| 스맥 | 099440 | industrial_robot_equipment | included | high | 공작기계·산업용 로봇 자동화 |
| HPSP | 403870 | ai_semiconductor_material_equipment | included | high | 고압 수소 어닐링 장비 |

## AI 반도체 소재·부품·장비

| 종목명 | 코드 | 사업내용 요약 | 포함 이유 | 근거 수준 | 검토 상태 |
|--------|------|---------------|-----------|-----------|-----------|
| 제이피아이헬스케어 | 0010V0 | 동사는 1980년 설립, 2010년 제이피아이헬스케어로 사명 변경함. 엑스선 기반 영상진단 부품 개발 및 제조를 주력으로 하고 있으며, GE,  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 디아이 | 003160 | 반도체 검사 보드 및 후공정 테스트 장비 | 후공정 테스트·검사. 소부장 장비 테마. | high / existing_verified_data | included |
| 동진쎄미켐 | 005290 | 포토레지스트(감광액) 등 전자재료 | 감광액 국산화 핵심. HBM·메모리 공정 연동. | high / existing_verified_data | included |
| 엠엑스로보틱스 | 007820 | 동사는 1972년 설립되어 1978년 자동화 창고 시스템을 국산화했고, 2017년 SK그룹에 편입됨. 일반물류, 반도체, 이차전지 등 다양한 산 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| HLB이노베이션 | 024850 | 동사는 1978년 반도체 부품 제조업으로 설립되어 2001년 코스닥 상장함. 반도체 IC와 TR용, 파워모듈용 프리몰드형 리드프레임, 테스트 소 | ai_semiconductor_material_equipment: 반도체, 테스트 (medium) | medium / business_description | included |
| 경창산업 | 024910 | 동사는 1961년 자전거 부품으로 시작해 1972년 자동차 부품 사업을 시작했으며, 1977년 법인전환 후 1994년 코스닥시장에 상장했음. 현 | ai_semiconductor_material_equipment: 파운드리 (needs_review) | needs_review / business_description | needs_review |
| 원익홀딩스 | 030530 | 동사는 1991년 반도체 장비 제조 및 판매 목적으로 설립되어 1996년 코스닥시장 상장하였고 2025년 기준 15개 종속회사 보유한 사업형 지 | ai_semiconductor_material_equipment: 반도체 장비, 반도체 (high) | high / business_description | included |
| 피에스케이홀딩스 | 031980 | 동사는 1990년 설립되고 1997년 코스닥에 상장, 2019년 인적분할로 피에스케이홀딩스와 피에스케이로 분리 후 2020년 합병하였음. 반도체 | ai_semiconductor_material_equipment: 반도체 패키징, 반도체, 패키징 (high | high / business_description | included |
| 피델릭스 | 032580 | 동사는 1990년 메모리 반도체 설계·판매를 목적으로 설립된 Fabless 전문회사로 1997년 코스닥에 상장함. DRAM, Flash Memo | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 엠케이전자 | 033160 | 동사는 1982년 설립되어 1997년 코스닥시장에 상장하였으며, 22개의 종속회사를 보유하고 있음. 본딩와이어와 솔더볼을 주력으로 생산하는 후공 | ai_semiconductor_material_equipment: 후공정, 본딩와이어, 패키징 (high) | high / business_description | included |
| 시그네틱스 | 033170 | 동사는 1966년 설립되어 2010년 코스닥시장에 상장한 반도체 패키징 전문기업임. 반도체 후공정 중 패키징 사업을 주목적으로 하며, 칩에 전기 | ai_semiconductor_material_equipment: 후공정, 반도체 패키징, 반도체 후공정,  | high / business_description | included |
| 네패스 | 033640 | 동사는 1990년 반도체 및 전자관련 부품 제조·판매를 목적으로 설립되어 1999년 코스닥시장에 상장함. 시스템 반도체의 소형화·고성능화에 기여 | ai_semiconductor_material_equipment: 후공정, 반도체, 패키징, 파운드리 (hi | high / business_description | included |
| 해성산업 | 034810 | 동사는 1954년 설립되어 1999년 코스닥시장에 상장한 지주회사로, 2020년 舊 한국제지㈜ 합병과 2021년 계양전기㈜, 해성디에스㈜의 현물 | ai_semiconductor_material_equipment: 반도체, 패키징 (medium) | medium / business_description | included |
| 위지트 | 036090 | 동사는 1997년 설립되어 1999년 코스닥에 상장한 반도체 및 디스플레이 제조 장비용 핵심부품 제조 전문기업임. 국내 최초로 디스플레이 소모성 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 에이치엠넥스 | 036170 | 동사는 1993년 자동조정 및 제어장치 제조·판매 목적으로 설립되어 1999년 코스닥 상장함. LED 패키지 생산을 주사업으로 하며 현대기아차  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 유니셈 | 036200 | 동사는 1988년 설립하고 1999년 코스닥에 상장한 반도체 장비 전문기업임. 국내 최초 Scrubber 개발 업체로, 반도체/디스플레이 제조  | ai_semiconductor_material_equipment: 반도체 장비, 스크러버, Scrubber, | high / business_description | included |
| SFA반도체 | 036540 | 동사는 1998년 설립되어 2001년 코스닥 상장한 반도체 후공정 전문기업으로, 삼성전자, Micron, SK하이닉스 등에 최첨단 패키징 솔루션 | ai_semiconductor_material_equipment: 후공정, 반도체 후공정, 반도체, 패키징  | high / business_description | included |
| 에프에스티 | 036810 | 펠리클 및 칠러(온도조절장치) 제조 | 펠리클·칠러. 공정 안정화 소부장. | high / existing_verified_data | included |
| 주성엔지니어링 | 036930 | 동사는 1993년 반도체 및 태양전지, 디스플레이 제조장비 제조·판매 목적 설립되어 1999년 코스닥시장에 상장됨. 반도체 제조장비(SD Sys | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 성도이엔지 | 037350 | 동사는 1987년 반도체장비 설비공사 설립되었으며, 1999년 성도이엔지로 변경 후 2000년 코스닥에 상장함. 동사는 첨단산업의 크린룸 설비공 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 아이에이 | 038880 | 동사는 1993년 반도체 개발 설계를 목적으로 설립되어 2000년 코스닥시장에 상장함. 비메모리 반도체 및 모듈 전문기업으로 자동차 전장용 반도 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 현대에이치티 | 039010 | 동사는 1998년 하이닉스반도체 사업구조조정에 따라 HA 사업부문이 분사되어 설립되었으며, 2000년 코스닥 시장에 상장되었음. 국내 최초 무인 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 이오테크닉스 | 039030 | 동사는 1989년 설립, 2000년 코스닥시장에 상장된 레이저 응용기기 전문기업으로, 현재 10개의 종속회사를 보유하고 있음. 반도체용 레이저마 | ai_semiconductor_material_equipment: 반도체용, 반도체 (high) | high / business_description | included |
| 에스티아이 | 039440 | 약품공급장치 및 세정 장비 | 약품·세정 장비. 라인 증설·리필 주기. | high / existing_verified_data | included |
| 아이씨디 | 040910 | 동사는 2000년 LCD, 반도체 및 평판 디스플레이 장비 제조를 목적으로 설립했으며, 2018년 물적분할로 아이씨디 머트리얼즈를 설립함. LC | ai_semiconductor_material_equipment: 식각, 증착, 반도체 (high) | high / business_description | included |
| 이엘씨 | 041520 | 동사는 1984년 설립되었으며 제어계측기기 제조 및 반도체 장비 사업을 하고 있음. 2020년 서우테크놀로지 인수로 반도체 PKG 설비 공급 사 | ai_semiconductor_material_equipment: 반도체 장비, 세정, 반도체 (high) | high / business_description | included |
| 성호전자 | 043260 | 동사는 1973년 진영전자로 설립 후 2000년 성호전자주식회사로 사명을 변경하고, 2001년 코스닥에 상장함. 2024년 중 ㈜제이케이아이홀딩 | ai_semiconductor_material_equipment: 증착 (high) | high / business_description | included |
| 웰킵스하이텍 | 043590 | 동사는 1974년 IT전자부품 전문기업으로 설립되어 2001년 코스닥 상장, 2024년 (주)제원테크 지분 100% 취득함. Display Dr | ai_semiconductor_material_equipment: 반도체, 패키징 (medium) | medium / business_description | included |
| 한양이엔지 | 045100 | 동사는 1988년 반도체 설비 업체로 설립되어 2000년에 코스닥에 상장했으며, 국내 최초로 초고순도 배관 국산화에 성공함. 반도체 및 디스플레 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 성우테크론 | 045300 | 동사는 1997년 반도체 검사장비 및 부품 제조를 주업으로 설립되어 코스닥시장에 상장함. 부품사업부는 메모리 칩 핵심부품 및 차량, 항공기, T | ai_semiconductor_material_equipment: 반도체 검사, 반도체 (high) | high / business_description | included |
| 코아시아 | 045970 | 동사는 1993년 설립되어 2000년 코스닥 상장한 시스템 반도체 및 전자부품 제조 전문기업임. 삼성 파운드리 공식 파트너로 시스템 반도체 사업 | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 서울반도체 | 046890 | 동사는 1987년 설립, 2002년 코스닥에 상장된 종합 LED 기업으로, 계열사에서 LED 칩을 받아 패키징해 판매하고 있음. LED 제품을  | ai_semiconductor_material_equipment: 패키징 (needs_review) | needs_review / business_description | needs_review |
| 기가레인 | 049080 | 동사는 2000년 설립되어 반도체 장비를 제조하며, 2012년 합병을 통해 RF 통신부품 사업을 확장함. 2024년 중국 우시에 반도체 장비 대 | ai_semiconductor_material_equipment: 반도체 장비, 식각, 반도체 (high) | high / business_description | included |
| 미래컴퍼니 | 049950 | 동사는 1984년 설립하여 2005년 코스닥시장에 상장한 반도체 및 디스플레이 제조장비 생산 기업임. 디스플레이 패널 가공 분야에서 글로벌 최고 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 비케이홀딩스 | 050090 | 동사는 2000년 설립, 2004년 코스닥 상장된 중소기업으로 경북 구미본사와 서울지점 운영함. 2023년 반도체소재 사업부문 영업정지 결정 후 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 에스폴리텍 | 050760 | 동사는 1999년 반도체 제조회사로 설립되어 2006년 주식회사 에스폴리텍으로 상호 변경 후 2002년 코스닥시장에 상장함. PC/PMMA 시트 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 아모텍 | 052710 | 동사는 1994년 전자 부품 제조 및 판매를 위해 설립되고, 1999년 Motor 사업과 Varistor 사업을 흡수 합병하며 (주)아모텍으로  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 아이앤씨 | 052860 | 동사는 1996년 설립된 시스템 반도체 설계 전문기업으로 2009년 코스닥 상장하였으며, 스마트에너지, 무선, 멀티미디어, AE 사업을 영위하고 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| KX하이텍 | 052900 | 동사는 1997년 범일엔지니어링으로 설립되었고, 2005년 코스닥에 상장, 2022년 케이엑스하이텍으로 이름을 변경함. 반도체 제조 전후공정 부 | ai_semiconductor_material_equipment: 후공정, 반도체, 패키징 (high) | high / business_description | included |
| 세동 | 053060 | 동사는 1986년 설립, 2001년 코스닥 상장한 자동차 부품 제조업체로, 금속압출물, 일반압출물 등 자동차 외장부품을 개발해 현대/기아차에 공 | ai_semiconductor_material_equipment: 증착, PVD (high) | high / business_description | included |
| 프로텍 | 053610 | 동사는 1997년에 반도체장비 및 자동화공압부품 제조를 위해 설립되고, 2001년 코스닥에 상장함. 또한, 2012년 일본 MINAMI CO., | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 텔레칩스 | 054450 | 동사는 1999년 설립되어 멀티미디어와 통신 관련 시장의 핵심 Chip 및 Total Solution 개발과 판매를 주요사업으로 하며 2004년 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| APS | 054620 | 동사는 1994년 반도체장비 및 소프트웨어 제조업을 목적으로 설립되고 2017년 장비사업을 분할하며, 2023년 사명을 APS로 변경함. 지주부 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 리노공업 | 058470 | 동사는 1978년 창업 후 1996년 법인전환, 2001년 코스닥 상장하여 검사용 프로브와 반도체 검사용 소켓을 자체 브랜드로 개발·제조·판매하 | ai_semiconductor_material_equipment: 반도체 검사, 반도체 (high) | high / business_description | included |
| 미코 | 059090 | 동사는 1999년 설립, 2002년 코스닥 상장한 중견기업으로, 2025년 금오테크놀로지 등 21개 종속기업 신규 연결하며 사업 확장함. 반도체 | ai_semiconductor_material_equipment: 세정, 반도체 (high) | high / business_description | included |
| 아진엑스텍 | 059120 | 동사는 1997년 주문형반도체 설계기술로 정밀모션제어기 개발을 위해 설립되고, 2014년 코스닥 상장함. 비메모리 반도체 설계기술로 산업용 모터 | ai_semiconductor_material_equipment: 반도체 장비, 반도체 (high) | high / business_description | included |
| 이엘피 | 063760 | 동사는 1999년 디스플레이 검사장비 제조 및 판매를 목적으로 설립되었으며, 2017년 코스닥 시장에 상장함. OLED 및 마이크로 디스플레이  | ai_semiconductor_material_equipment: 반도체 패키징, 반도체, 패키징 (high | high / business_description | included |
| 인텍플러스 | 064290 | 동사는 1995년 제어계측기기 및 컴퓨터 응용기기 제조를 목적으로 설립되었으며, 2011년 코스닥에 상장함. 머신비전기술로 3D/2D 자동외관검 | ai_semiconductor_material_equipment: 후공정, 반도체 후공정, 반도체 (high | high / business_description | included |
| 테크엘 | 064520 | 동사는 1998년 설립, 2002년 코스닥시장 상장된 반도체 후공정 전문기업임. 메모리 및 비메모리 반도체 패키징, 테스트 후공정 서비스 제공하 | ai_semiconductor_material_equipment: 웨이퍼, 후공정, 반도체 패키징, 반도체  | high / business_description | included |
| 티씨케이 | 064760 | 동사는 1996년 일본 TOKAI CARBON CO., LTD.와 케이씨, 슝크카본테크놀로지 합작으로 설립되어 2003년 코스닥에 상장함. 반도 | ai_semiconductor_material_equipment: CVD, 반도체 (high) | high / business_description | included |
| 큐에스아이 | 066310 | 동사는 2000년 반도체 레이저와 광반도체 제품 제조·판매를 목적으로 설립되었고, 2006년 코스닥에 상장됨. 반도체 레이저 원천기술 확보 및  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 한성크린텍 | 066980 | 동사는 1998년 설립되어 2023년 한성크린텍㈜를 흡수합병하며 한성크린텍 주식회사로 출범함. 전자 및 반도체 공정에 필요한 초순수, 폐수, 공 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 하나마이크론 | 067310 | 어드밴스드 패키징 및 테스트 | 선단 공정·HBM 밸류체인. 5만 원대 중반 가격대. | high / existing_verified_data | included |
| 엔브이에이치코리아 | 067570 | 동사는 1984년 설립 후 2001년 엔브이에이치코리아로 변경함. 2018년 케이엔솔 인수로 반도체 등 산업 진출, 2019년 삼현에이치 인수로 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 리튬포어스 | 073570 | 동사는 1998년 반도체 검사장비 개발 및 제조 사업으로 설립되어 2004년 코스닥시장에 상상함. 2019년 ㈜위드모바일을 합병하였으며, 202 | ai_semiconductor_material_equipment: 반도체 검사, 반도체 (high) | high / business_description | included |
| 원익QnC | 074600 | 식각 공정용 쿼츠웨어 제조 | 식각 쿼츠웨어. 5만 원대 이하 밸류체인. | high / existing_verified_data | included |
| 덕산하이메탈 | 077360 | 동사는 1999년 반도체 소재·부품 제조 및 판매를 주력으로 설립되고, 미얀마 현지법인 설립과 덕산넵코어스, 덕산에테르씨티 인수 통해 사업 확장 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 국일제지 | 078130 | 동사는 1978년 설립된 특수지 제조·판매 기업으로, 2018년 그래핀 및 신소재 연구개발을 위해 자회사 국일그래핀(주)를 설립함. 산업용 기능 | ai_semiconductor_material_equipment: CVD (high) | high / business_description | included |
| 한양디지텍 | 078350 | 동사는 2004년 한양이엔지(주) 메모리모듈 제조 사업부문에서 인적분할되어 설립되었고, 코스닥시장에 직상장되었음. 반도체 메모리모듈과 SSD 제 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 제주반도체 | 080220 | 동사는 2000년 설립되어 2005년 코스닥 상장한 모바일 응용기기용 메모리 반도체 개발·제조 팹리스 기업임. 저전력 SRAM, Pseudo S | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 오디텍 | 080520 | 동사는 1999년 설립되어 2007년 코스닥에 상장된 반도체 전문기업으로, 2025년 베트남에 ODT VINA Co.,Ltd.를 설립해 글로벌  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 오킨스전자 | 080580 | 동사는 1998년 반도체 검사용 소켓 제조를 목적으로 설립되어 2014년 코스닥에 상장하고, 2006년 반도체 사업부를 설립하여 후공정 테스트  | ai_semiconductor_material_equipment: 후공정, 반도체 검사, 반도체, 테스트 ( | high / business_description | included |
| 엘오티베큠 | 083310 | 반도체용 건식 진공펌프 제조 | 건식 진공펌프. 공정 장비 핵심 부품. | high / existing_verified_data | included |
| GST | 083450 | 동사는 2001년 설립 후 2006년 코스닥에 상장했으며, 글로벌 거점 확대로 해외 판매망 강화 중임. 반도체 및 디스플레이 제조공정에서 배출되 | ai_semiconductor_material_equipment: 플라즈마, Scrubber, 반도체 (hi | high / business_description | included |
| 에프엔에스테크 | 083500 | 동사는 2002년 평판디스플레이 관련 장비와 반도체 제조용 부품소재 제조 및 판매를 목적으로 설립됨. 동사는 대만 회사 지분을 2025년 취득하 | ai_semiconductor_material_equipment: 식각, 세정, CMP, 반도체 (high) | high / business_description | included |
| 케이엠 | 083550 | 동사는 1989년 설립되어 클린룸 소모품 제조를 시작으로 현재 크린룸소모품, 생활용품, BLU 가공 등으로 사업을 확장하며 성장함. 국내 주요  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 유진테크 | 084370 | 동사는 2000년 반도체 장비 제조업체로 설립, 2006년 코스닥 상장하였으며, 3개의 종속회사 보유함. 반도체 전공정 웨이퍼 처리공정 중 박막 | ai_semiconductor_material_equipment: 반도체 장비, 웨이퍼, 전공정, 반도체 전 | high / business_description | included |
| 픽셀플러스 | 087600 | 동사는 2000년 CMOS 이미지센서 및 카메라모듈 개발·제조·공급을 목적으로 설립되어 2015년 코스닥에 상장함. CIS 및 Image Pro | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 동아엘텍 | 088130 | 동사는 1999년 법인전환되어 2007년 코스닥시장에 상장되었으며, 2009년 (주)선익시스템을 인수하여 핵심장비 일관생산능력을 확보함. OLE | ai_semiconductor_material_equipment: 증착, 후공정 (high) | high / business_description | included |
| 쏘닉스 | 088280 | 동사는 2000년 설립되어 RF 부품인 SAW 필터를 설계, 생산, 판매하던 회사로 시작함. 2015년 이후 5G 스마트폰 성능 향상으로 RF  | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 이녹스 | 088390 | 동사는 2001년 새한마이크로닉스로 시작하여 2005년 사명을 이녹스로 변경 후 2017년 이녹스와 이녹스첨단소재로 분할함. 이녹스 그룹 지주사 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 켐트로닉스 | 089010 | 동사는 1983년 설립되어 2007년 코스닥에 상장한 반도체·전자·전장 소재 및 부품 전문기업임. 반도체 PR/세정 공정용 소재, 유리기판 가공 | ai_semiconductor_material_equipment: 웨이퍼, 식각, 세정, 반도체 (high) | high / business_description | included |
| 테크윙 | 089030 | 메모리 테스트 핸들러 | 테스트 핸들러. 메모리 CAPEX·검증 장비. | high / existing_verified_data | included |
| 제이티 | 089790 | 동사는 2006년 코스닥에 상장한 반도체 검사 장비 제조 기업으로, 최종 검사 장비를 개발·제조함. 삼성전자 등 글로벌 메모리 반도체 기업에 B | ai_semiconductor_material_equipment: HBM, 반도체 검사, 반도체 (high) | high / business_description | included |
| 유비벨록스 | 089850 | 동사는 2000년 설립되어 2010년 코스닥 상장한 중견기업으로, 2025년 K컬쳐 액세서리 사업 진출 위해 이룸디자인스킨을 신규 연결함. Se | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 브이엠 | 089970 | 동사는 2002년 설립된 반도체 건식 식각장비 제조업체로, 2018년 코스닥 상장 후 미국과 중국에 현지법인을 보유하고 있음. 300mm 실리콘 | ai_semiconductor_material_equipment: 식각, 건식, 플라즈마, 반도체 (high | high / business_description | included |
| 로보스타 | 090360 | 동사는 1999년 설립되어 2011년 코스닥 상장한 산업용 로봇 전문업체임. 직각좌표, 수평·수직다관절 로봇과 AGV, AMR 등의 로봇을 공급 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 비에이치 | 090460 | 모바일/IT기기 연성회로기판 | 연성기판 수요. IT 출하·재고 사이클 민감. | high / existing_verified_data | included |
| 한울소재과학 | 091440 | 동사는 2000년 유선통신기기 제조 및 판매를 목적으로 설립되었으며, 이후 제이케이머트리얼즈와 협력하여 반도체 소재사업으로 사업 영역을 확대함. | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 디엔에프 | 092070 | 동사는 2001년 설립되어 2007년 코스닥 상장된 반도체 소자 형성용 박막 재료 전문기업임. DPT & QPT 재료, High-k 재료, 저온 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 서울바이오시스 | 092190 | 동사는 2002년 설립된 반도체 기반 소자 전문 기업으로 2020년 코스닥에 상장했으며, 6개 R&D 센터와 3개 해외 자회사를 운영함. 전 스 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 현우산업 | 092300 | 동사는 1987년 설립, 1996년 법인전환한 PCB 제조 전문기업임. 자동차 전장과 LCD, LED, OLED 등 디지털 가전기기에 장착되는  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 앤씨앤 | 092600 | 동사는 1997년 설립되어 2007년 코스닥시장에 상장하고, 2019년 물적분할로 반도체 사업을 분할해 넥스트칩을 설립하고 앤커넥트를 흡수합병하 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 엑시콘 | 092870 | 동사는 2001년 반도체 메모리 테스트 시스템 개발·제조·판매를 목적으로 설립되어 2014년 코넥스와 2015년 코스닥에 상장하였고, 일본 법인 | ai_semiconductor_material_equipment: 메모리 테스트, 테스트 장비, 반도체 검사 | high / business_description | included |
| 동운아나텍 | 094170 | 동사는 2015년 코스닥 상장한 시스템 반도체 전문 업체로, 반도체 칩 설계 후 파운드리에 위탁 생산하여 판매하고 있음. 스마트폰 카메라용 OI | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 칩스앤미디어 | 094360 | 동사는 2003년 설립된 반도체 설계자산 전문업체로, 비디오 코덱 IP를 제조사에 라이선스하여 반도체 칩 설계 및 개발을 지원함. 매출은 라이선 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 테스 | 095610 | 동사는 2002년 설립되어 2008년 코스닥 상장한 반도체 장비 제조 전문기업임. 반도체 전공정 핵심장비인 PECVD와 Etch & Cleani | ai_semiconductor_material_equipment: 반도체 장비, 식각, 전공정, 건식 (hi | high / business_description | included |
| 알에프세미 | 096610 | 동사는 1999년 반도체 소자 제조 및 판매 목적으로 설립되어 2007년 코스닥에 상장, 해외 2개 종속기업 운영 중임. ECM Chip, TV | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 엘디티 | 096870 | 동사는 1997년 설립된 팹리스 반도체 회사로, 2014년 아트시스템 합병으로 SSN과 NI사업을 추가함. 반도체사업부는 OLED 및 LED 디 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 윈팩 | 097800 | 동사는 2002년 설립돼 2013년 코스닥시장 상장한 반도체 후공정 전문기업임. 이 회사는 반도체 칩을 Substrate에 탑재해 전기적으로 연 | ai_semiconductor_material_equipment: 후공정, 반도체 후공정, 반도체, 패키징  | high / business_description | included |
| 마이크로컨텍솔 | 098120 | 동사는 1999년 반도체 검사용 아이씨소켓 제조를 목적으로 설립되었으며, 2022년 ㈜엠에스엘 지분 98.41% 취득으로 역량을 강화함. 반도체 | ai_semiconductor_material_equipment: 반도체 검사, 반도체 (high) | high / business_description | included |
| 고영 | 098460 | 동사는 2002년 검사 및 측정 자동화 시스템 제조 목적으로 설립되고 2008년 코스닥 상장함. 메카트로닉스, 광학, 비전, SW, AI 기술을 | ai_semiconductor_material_equipment: 후공정, 반도체, 패키징 (high) | high / business_description | included |
| 월덱스 | 101160 | 동사는 2000년 반도체 및 전자부품 제조 목적으로 설립되어 2008년 코스닥에 상장하고 2009년 미국 WCQ를 인수하여 소재 전문기업으로 성 | ai_semiconductor_material_equipment: 식각, 쿼츠, 반도체 (high) | high / business_description | included |
| 엔시트론 | 101400 | 동사는 2000년 설립 후 비메모리 반도체 제조·판매를 하며 2009년 코스닥에 상장함. 2024년 글로벌 셰프 브랜드 Gordon Ramsay | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 어보브반도체 | 102120 | 동사는 2006년 비메모리반도체 개발 및 제조를 목적으로 설립되었으며, 2009년 코스닥시장에 상장함. 주요종속회사인 (주)윈팩을 통해 반도체  | ai_semiconductor_material_equipment: 후공정, 반도체 후공정, 반도체, 패키징  | high / business_description | included |
| 이엔에프테크놀로지 | 102710 | 동사는 2000년 반도체/디스플레이 프로세스케미칼 제조 및 판매를 위해 설립되고, 2009년 코스닥시장에 상장함. 전자재료 사업부문은 특수 화학 | ai_semiconductor_material_equipment: 반도체용, 식각, 세정, CMP (high | high / business_description | included |
| 원익머트리얼즈 | 104830 | 반도체용 고순도 특수 가스 | 고순도 가스 공급. 메모리·파운드리 가동률 민감. | high / existing_verified_data | included |
| 케이엔더블유 | 105330 | 동사는 2001년 설립되었고 2009년 코스닥에 상장하였으며, 2023년 공정거래법에 따른 공시대상기업집단에 소속된 중견기업임. 전자부품소재와  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 와이씨켐 | 112290 | 동사는 2001년 설립되어 반도체 공정 재료 사업을 영위하며 2022년 코스닥에 상장됨. 특수 Surfactant 및 polymer로 ArF·E | ai_semiconductor_material_equipment: 세정, HBM, 포토레지스트, 반도체 (h | high / business_description | included |
| 한솔아이원스 | 114810 | 동사는 1993년 설립되어 2005년 법인전환 후 아이원스로 출범하였고 2013년 기업공개, 2022년 한솔그룹 편입에 따라 한솔아이원스로 사명 | ai_semiconductor_material_equipment: 반도체 장비, 세정, 반도체 (high) | high / business_description | included |
| 이미지스 | 115610 | 동사는 2010년 코스닥시장에 상장한 반도체 전문 팹리스 기업임. Touch Controller IC, Haptic Driver IC 등 모바일 | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 알파칩스 | 117670 | 동사는 2002년 설립되어 2003년 삼성전자 반도체 파운드리 디자인하우스로 지정되었고, 2019년 공식 디자인솔루션파트너로 승격되었음. 동사는 | ai_semiconductor_material_equipment: 반도체, 패키징, 테스트, 파운드리 (me | medium / business_description | included |
| 티로보틱스 | 117730 | 동사는 2004년 설립되어 자율주행 물류로봇과 반도체, 디스플레이용 진공로봇을 개발·제조하며, 2018년 코스닥에 상장함. 주요 사업은 물류이송 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 아이텍 | 119830 | 동사는 2005년 설립돼 2010년 코스닥 상장된 반도체 테스트 전문기업임. 반도체 기술서비스, 소프트웨어 개발, 전자 엔지니어링 서비스를 제공 | ai_semiconductor_material_equipment: 반도체, 테스트 (medium) | medium / business_description | included |
| KX | 122450 | 동사는 2000년 채널사용사업을 목적으로 설립, 2011년 코스닥 상장하였으며 주요 종속회사로 반도체 재료 제조 ㈜케이엑스하이텍 등을 보유함.  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 예스티 | 122640 | 동사는 2000년 설립된 반도체 및 디스플레이 열처리 장비 전문 기업으로, 2015년 코스닥시장에 상장하였음. 연결대상 종속회사로 예스히팅테크닉 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 알엔티엑스 | 123010 | 동사는 2003년 이미지센서 패키징 분야 특허기술로 설립되어 2016년 코스닥에 상장된 기술성장기업임. 이미지센서 패키징을 주력으로 하며 자동차 | ai_semiconductor_material_equipment: 패키징, 테스트 (medium); indu | needs_review / business_description | needs_review |
| 아나패스 | 123860 | 동사는 2002년 설립된 디스플레이용 시스템 반도체 전문 기업으로 2010년 코스닥시장에 상장함. 디스플레이 패널 핵심 부품인 T-Con과 TE | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 티에스이 | 131290 | 동사는 1995년 반도체 검사장비 제조·판매목적으로 설립되었으며, 2011년 기업공개를 했음. 또한 2020년 엘디티의 제3자배정 유상증자 참여 | ai_semiconductor_material_equipment: 반도체 검사, 반도체 (high) | high / business_description | included |
| 두산테스나 | 131970 | 동사는 2002년 TESNA Inc.로 설립되어 시스템 반도체 후공정 중 테스트 사업을 전문적으로 영위하며, 2022년 두산테스나로 상호를 변경 | ai_semiconductor_material_equipment: 웨이퍼, 후공정, 반도체 후공정, 반도체  | high / business_description | included |
| 비아트론 | 141000 | 동사는 2001년 반도체 및 평판디스플레이 제조용 기계제조업 등을 목적으로 설립되어 지속하고 있음. 디스플레이 TFT Backplane 공정의  | ai_semiconductor_material_equipment: CVD, 패키징 장비, 반도체, 패키징 ( | high / business_description | included |
| 뉴파워프라즈마 | 144960 | 동사는 1993년 설립되어 2002년 세계 두 번째로 반도체 및 FPD 공정용 Remote Plasma Generator를 개발함. 주요 제품으 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 비씨엔씨 | 146320 | 동사는 2003년 설립된 반도체 제조 공정용 소모 부품 전문기업으로, 2022년 코스닥에 상장하였음. 반도체 식각 및 박막 증착 공정에 쓰이는  | ai_semiconductor_material_equipment: 식각, 증착, 쿼츠, CVD (high) | high / business_description | included |
| 피엠티 | 147760 | 동사는 2004년 설립되어 MEMS 기술 기반 3D MEMS 프로브 카드를 개발 상용화하고, 2016년 코스닥에 상장함. 반도체 웨이퍼 테스트용 | ai_semiconductor_material_equipment: 웨이퍼, 반도체, 테스트 (high) | high / business_description | included |
| 알엔투테크놀로지 | 148250 | 동사는 2016년 코넥스기업에서 코스닥시장으로 신속이전상장을 하였으며, 원천소재 기술을 바탕으로 통신 기지국용 부품과 의료기기용 다층세라믹 기판 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 아바텍 | 149950 | 동사는 2000년 Display용 진공박막코팅 제품 생산과 판매를 위해 설립되어, 2011년 구미공장 준공 후 Glass Slimming, IT | ai_semiconductor_material_equipment: 식각 (high) | high / business_description | included |
| 와이엠씨 | 155650 | 동사는 2008년 설립되어 2012년 코스닥 상장한 디스플레이 및 반도체 소재, 부품 전문기업임. 디스플레이 증착공정의 타겟과 Backing P | ai_semiconductor_material_equipment: 증착, 반도체 (high) | high / business_description | included |
| 싸이맥스 | 160980 | 동사는 2005년 설립되어 2015년 코스닥에 상장한 반도체 장비 전문기업으로, 웨이퍼 이송장비 CTS, EFEM, LPM을 제조하며 국내 매출 | ai_semiconductor_material_equipment: 반도체 장비, 웨이퍼, 반도체 (high) | high / business_description | included |
| 펨트론 | 168360 | 동사는 2002년 설립된 3D 정밀공정검사장비 전문기업으로, 2022년 코스닥 상장 후 홍콩, 미국 등 해외법인을 운영 중임. 3D 측정 및 A | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 엘티씨 | 170920 | 동사는 2007년 설립되어 2013년 코스닥시장에 상장하고, 디스플레이 및 반도체용 PR 박리액 개발 및 제조를 주력사업으로 함. 종속회사 엘티 | ai_semiconductor_material_equipment: 반도체용, 웨이퍼, 식각, 세정 (high | high / business_description | included |
| 램테크놀러지 | 171010 | 동사는 2001년 반도체용 식각액 및 IT 화학소재 제조·판매를 위해 설립되어 2013년 코스닥에 상장함. 반도체 공정용 화학소재 제조를 기반으 | ai_semiconductor_material_equipment: 반도체용, 식각, 반도체 (high) | high / business_description | included |
| 선익시스템 | 171090 | 동사는 1990년 설립되어 OLED 장비 제조 및 판매를 주력으로 하고 있으며, 2024년 중국 고객사와 대형 증착기 공급 계약을 체결하였음.  | ai_semiconductor_material_equipment: 증착 (high) | high / business_description | included |
| 에이엘티 | 172670 | 동사는 2003년 설립되어 비메모리 반도체 후공정 테스트를 전문적으로 수행하고, 종속회사 에이지피는 CIS 패키징 사업을 진행하고 있음. DDI | ai_semiconductor_material_equipment: 후공정, 반도체 후공정, 반도체, 패키징  | high / business_description | included |
| 코미코 | 183300 | 동사는 2013년 코미코의 정밀세정 및 특수코팅 사업 부문을 물적분할하여 설립되었으며, 중국과 일본 등 9개 종속회사를 연결함. 반도체 공정 장 | ai_semiconductor_material_equipment: 세정, 반도체 (high) | high / business_description | included |
| 디바이스 | 187870 | 동사는 2002년 반도체 및 디스플레이 장비 제조를 목적으로 설립되었고, 2017년 코스닥에 상장됨. 주요 사업으로 OLED 증착 공정용 디스플 | ai_semiconductor_material_equipment: 웨이퍼, 식각, 증착, 세정 (high) | high / business_description | included |
| 에이팩트 | 200470 | 동사는 2007년 SK하이닉스 협의회 회원사들이 공동 출자하여 설립되었으며, 패키징 사업 양수로 반도체 후공정 일괄 생산체제를 구축하고 글로원아 | ai_semiconductor_material_equipment: 후공정, 전공정, 반도체 후공정, 반도체  | high / business_description | included |
| 에이디테크놀로지 | 200710 | 동사는 2002년 설립되어 반도체 설계 및 개발에 특화된 국내 시스템 반도체 디자인하우스 선도기업임. TSMC의 가치사슬협력자로 시작해 2020 | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 제이앤티씨 | 204270 | 동사는 1996년 설립, 2020년 코스닥 상장된 첨단소재 및 고정밀 부품 제조업체로, 100% 자회사인 베트남 법인 운영 중임. 강화유리를 포 | ai_semiconductor_material_equipment: 반도체용, 반도체 (high) | high / business_description | included |
| 와이제이링크 | 209640 | 동사는 2009년 설립되어 2024년 코스닥시장에 상장하고, 태국법인 설립으로 PCB어셈블리 제조 및 판매 사업을 확장함. 스마트화를 위한 SM | ai_semiconductor_material_equipment: 후공정 (high); industrial_ | needs_review / business_description | needs_review |
| 아이에스티이 | 212710 | 동사는 2013년 설립되어 반도체 장비를 중심으로 OLED, LCD, 자동차 등 다양한 산업의 장비 및 부품을 판매하는 장비사업과 수소에너지 중 | ai_semiconductor_material_equipment: 반도체 장비, CVD, 반도체 (high) | high / business_description | included |
| 제너셈 | 217190 | 동사는 2000년 반도체 후공정 자동화 장비 전문기업으로 설립되어 인천 송도 본사에서 영업 중임. HBM Automation, EMI Shiel | ai_semiconductor_material_equipment: HBM, 후공정, 반도체 후공정, 반도체  | high / business_description | included |
| 러셀 | 217500 | 동사는 2006년 반도체 장비 리퍼비시 전문기업으로 설립되어 2018년 코스닥 합병상장함. 동사는 반도체 전공정 내 증착장비 리퍼비시와 무인자동 | ai_semiconductor_material_equipment: 반도체 장비, 증착, 전공정, 반도체 전공 | high / business_description | included |
| RFHIC | 218410 | 동사는 1999년 질화갈륨 반도체 전문기업으로 설립되어 2017년 코스닥 상장하고, 2025년 RFHIC Europe 신규 설립함. 무선통신,  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 타이거일렉 | 219130 | 동사는 2000년 인쇄회로기판 제조 및 판매를 목적으로 설립되었으며 2011년 ㈜티에스이의 자회사로 편입되며 Tigerelec㈜로 상호 변경하였 | ai_semiconductor_material_equipment: 후공정, 반도체 검사, 반도체 (high) | high / business_description | included |
| 링크제니시스 | 219420 | 동사는 2003년 설립된 소프트웨어 개발 전문기업으로, 2018년 코스닥시장 상장하였으며, 2014년 ㈜아이티이노베이션 인수로 사업영역을 확장함 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 심텍 | 222800 | 동사는 1987년 설립되어 PCB 제조 및 판매를 하다가 2015년 인적 분할을 통해 신설되었으며, 국내외 법인을 운영하고 있음. 반도체용 PC | ai_semiconductor_material_equipment: 반도체용, 반도체, 패키징 (high) | high / business_description | included |
| 엠디바이스 | 226590 | 동사는 2009년 설립되어 2025년 코스닥시장에 이익미실현기업 특례상장하였으며, 같은 해 자회사를 신규 설립함. 메모리 반도체와 시스템 반도체 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 와이씨 | 232140 | 동사는 1991년 설립, 2012년 메모리 테스터 부문 인수, 2015년 에이티테크놀로지 인수로 장비 유지보수 역량 확보함. DRAM 및 NAN | ai_semiconductor_material_equipment: 웨이퍼, HBM, 전공정 (high) | high / business_description | included |
| 싸이닉솔루션 | 234030 | 동사는 2005년 설립된 시스템 반도체 디자인하우스 기업으로 코스닥시장에 상장함. SK하이닉스시스템아이씨의 공식 파운드리 판매대행 협력사이자 디 | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 힘스 | 238490 | 동사는 1999년 OLED 등 평판디스플레이 관련 장비와 부품 제조 및 판매를 목적으로 설립되어 2017년 코스닥시장에 상장함. 동사는 글로벌  | ai_semiconductor_material_equipment: 증착, 후공정, 반도체 후공정, 반도체 ( | high / business_description | included |
| 원익IPS | 240810 | 동사는 2016년 반도체, Display, Solar Cell 장비 사업부문 인적분할로 설립되어 코스닥시장에 상장함. 반도체 제조공정 중 박막  | ai_semiconductor_material_equipment: 증착, CVD, 반도체 (high) | high / business_description | included |
| 메카로 | 241770 | 동사는 2000년 반도체 소재·부품·장비 국산화를 목표로 설립되어 2017년 코스닥 상장함. 동사는 웨이퍼를 흡착·가열하는 메탈히터블럭을 주력  | ai_semiconductor_material_equipment: 웨이퍼, 반도체 (high) | high / business_description | included |
| 와이엠티 | 251370 | 동사는 1999년 전자 화학소재 분야 전문기업으로 설립되어 2017년 코스닥에 상장함. 와이피티㈜, YMT Shenzhen, YMT Specia | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 샘씨엔에스 | 252990 | 동사는 2016년 설립되어 2021년 코스닥시장에 상장된 반도체 테스트 장비 핵심부품 제조기업임. 프로브카드용 세라믹STF를 제작하여 납품하며, | ai_semiconductor_material_equipment: 웨이퍼, 테스트 장비, 반도체, 테스트 ( | high / business_description | included |
| 네오셈 | 253590 | 동사는 2002년 반도체 후공정 검사장비 업체로 설립되어 2019년 대신밸런스제3호기업인수목적(주)와의 합병을 통해 코스닥 시장에 등록됨. 메모 | ai_semiconductor_material_equipment: 후공정, 반도체 후공정, 반도체 (high | high / business_description | included |
| 야스 | 255440 | 동사는 2002년 설립, 2017년 코스닥 상장하고 Fab1~3 공장을 보유하며 8.6세대 제조 위한 Fab4 가동 준비 중임. OLED 디스플 | ai_semiconductor_material_equipment: 증착 (high); industrial_r | needs_review / business_description | needs_review |
| 포인트엔지니어링 | 256630 | 동사는 1998년 설립된 반도체 및 디스플레이 제조장비 부품의 표면처리 전문업체로, 2019년 코스닥에 상장함. 반도체 및 디스플레이 공정의 핵 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 휴엠앤씨 | 263920 | 동사는 2002년 설립 후 2022년 휴엠앤씨로 상호 변경, 2017년 코스닥시장에 상장됨. 주력 사업으로 의료용 유리용기, 제약회사의 주사제  | ai_semiconductor_material_equipment: 패키징 (needs_review) | needs_review / business_description | needs_review |
| 씨앤지하이테크 | 264660 | 동사는 2002년 설립되어 2018년 코스닥 상장한 반도체 제조용 장비 업체임. 반도체/디스플레이 공정에 필요한 화학약품을 자동 공급하는 CCS | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 시스웍 | 269620 | 동사는 2004년 설립, 2017년 코스닥 상장한 시스템장치제어 하드웨어 제조업체임. 디스플레이 및 반도체 클린룸용 FFU, EFU 모터와 제어 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 팸텍 | 271830 | 동사는 2005년 자동화장비 전문기업으로 설립, 2023년 코스닥시장에 상장되었으며, 베트남과 중국에 현지 법인을 운영하고 있음. 스마트폰 탑재 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 케이엔제이 | 272110 | 동사는 2005년 반도체 제조용 CVD-SiC Product 생산을 목적으로 설립되었음. 반도체 웨이퍼 에칭공정용 SiC Focus Ring 및 | ai_semiconductor_material_equipment: 웨이퍼, 증착, CVD, 반도체 (high | high / business_description | included |
| 레이크머티리얼즈 | 281740 | 동사는 2010년 설립되어 2020년 코스닥에 상장함. 반도체, Solar, LED, 메탈로센촉매, 디스플레이 소재로 쓰이는 초고순도 유기금속화 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 케이씨텍 | 281820 | CMP(화학적 기계 연마) 장비 및 소재 | CMP 장비·소재. 후공정 연마 수요. | high / existing_verified_data | included |
| 웨이비스 | 289930 | 동사는 2017년 설립되어 2024년 코스닥시장에 상장하였으며, 국내 최초로 GaN RF 반도체 칩 양산 기술을 보유한 전문기업임. 칩-패키지- | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 트윔 | 290090 | 동사는 2010년 설립되어 AI검사기를 연구개발 및 판매하며, 2021년 코스닥시장에 상장함. 반도체, 디스플레이 등 다양한 분야에 공정자동화  | ai_semiconductor_material_equipment: 후공정, 반도체 (high) | high / business_description | included |
| HB솔루션 | 297890 | 동사는 2001년 설립되어 레진 도포, 접합 및 검사 설비 제작 기술을 바탕으로 디스플레이 전후공정 설비와 반도체 측정·검사 및 제조설비를 생산 | ai_semiconductor_material_equipment: 후공정, 전공정, 반도체 (high) | high / business_description | included |
| 지니틱스 | 303030 | 동사는 2000년 설립된 시스템 반도체 설계 전문 기업으로, 2019년 역합병하여 코스닥시장에 상장함. 터치 컨트롤러 IC를 핵심으로 AF Dr | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 지아이에스 | 306620 | 동사는 2000년 반도체, 디스플레이, MLCC용 절단장비 제조 및 판매를 목적으로 설립되었으며, 2020년 경영효율성 및 인력유치 재무 개선을 | ai_semiconductor_material_equipment: 세정, 반도체 (high) | high / business_description | included |
| 지오엘리먼트 | 311320 | 동사는 2005년 설립 후 2021년 코스닥에 상장하고, 2024년 (주)지오어플라이언스 지분 신규 취득함. 반도체사업부에서 전구체 기화이송 기 | ai_semiconductor_material_equipment: 반도체용, 반도체 (high) | high / business_description | included |
| 라닉스 | 317120 | 동사는 2003년 설립되어 무선통신과 보안 시스템반도체 및 솔루션 개발을 진행함. 자율주행차의 WAVE-V2X 통신 솔루션을 개발 및 사업화하고 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 덕산테코피아 | 317330 | 동사는 2006년 전자부품 제조업을 위해 설립되어 2019년에 코스닥 상장, 계열사로 (주)덕산퓨처셀 등을 보유함. OLED 핵심구성요소인 유기 | ai_semiconductor_material_equipment: 반도체용, 증착, 반도체 (high) | high / business_description | included |
| 피에스케이 | 319660 | 전공정 PR 스트립(감광액 제거) 장비 | PR 스트립 장비 글로벌 1위. HBM·선단 공정 수혜. | high / existing_verified_data | included |
| 한울반도체 | 320000 | 동사는 1999년 설립되어 2020년 하나금융13호기업인수목적 주식회사와 합병 완료 및 6개 종속회사 신규 연결함. 머신비전 기술로 MLCC 등 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 프로이천 | 321260 | 동사는 2006년 설립되어 코스닥시장에 상장됨. 세계 최초 필름형 프로브 블록 특허를 기반으로 디스플레이 및 반도체 검사장치를 제조하며, 삼성디 | ai_semiconductor_material_equipment: 반도체 검사, 반도체 (high) | high / business_description | included |
| 오로스테크놀로지 | 322310 | 오버레이(정렬) 계측 장비 국산화 | 오버레이 계측 국산화. 선단 공정 품질 관련. | high / existing_verified_data | included |
| 다원넥스뷰 | 323350 | 동사는 2009년 레이저장비 제조 및 판매를 목적으로 설립되어 2024년 기술성장기업 특례로 코스닥시장에 상장함. 반도체 테스트 및 패키징 공정 | ai_semiconductor_material_equipment: HBM, 반도체, 패키징, 테스트 (hig | high / business_description | included |
| RF머트리얼즈 | 327260 | 동사는 2007년 설립 후 2019년 코스닥 상장한 화합물 반도체 패키지 전문기업임. 광통신 패키지, RF Power 트랜지스터 패키지 등 화합 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 네패스아크 | 330860 | 동사는 2019년 네패스 반도체사업부 내 Test 사업부문이 물적 분할되어 설립되고 2020년 코스닥시장에 상장됨. 시스템반도체 후공정 테스트  | ai_semiconductor_material_equipment: 후공정, 테스트 장비, 반도체 후공정, 반 | high / business_description | included |
| 센코 | 347000 | 동사는 2004년 설립되어 2020년 코스닥에 상장한 가스 안전 분야 선도기업임. 전기화학식 가스 센서 및 가스 감지기를 핵심 제품으로 하며,  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 핌스 | 347770 | 동사는 2016년 OLED 디스플레이 메탈마스크 제작을 주요 사업으로 설립되었으며, 2022년 메탈마스크 프레임 업체를 인수하여 사업을 내재화함 | ai_semiconductor_material_equipment: 증착 (high) | high / business_description | included |
| 넥스틴 | 348210 | 동사는 2010년 설립된 반도체 전공정 검사 장비 제조 전문기업으로, 2020년 코스닥 상장 후 사업 영역을 확대함. 광학 이미지 비교방식으로  | ai_semiconductor_material_equipment: HBM, 전공정, 반도체 전공정, 반도체  | high / business_description | included |
| 위드텍 | 348350 | 동사는 2003년 환경산업 분야의 고감도 정밀측정과 오염제어 기술 개발을 목적으로 설립되었으며, 2020년 코스닥시장에 상장함. 반도체·디스플레 | ai_semiconductor_material_equipment: 반도체 (needs_review); pow | needs_review / business_description | needs_review |
| 코스텍시스 | 355150 | 동사는 2013년 설립되어 반도체 패키징용 방열 소재 및 부품을 개발·생산하며, 2023년 코스닥시장에 상장함. RF 통신 패키지, 전력 반도체 | ai_semiconductor_material_equipment: 반도체용, 반도체 패키징, 반도체, 패키징 | needs_review / business_description | needs_review |
| 하이딥 | 365590 | 동사는 2010년 설립되어 2022년 코스닥에 상장한 팹리스 회사로, 모바일 기기의 UX/UI, 하드웨어, 소프트웨어, 반도체 IC 등 솔루션을 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 오에스피 | 368970 | 동사는 2004년 충남 논산에서 창립하여 종이포장지 제조업을 하다가 2011년 반려동물용 배합사료 제조로 사업을 확장했음. 2012년 펫푸드 전 | ai_semiconductor_material_equipment: 건식 (high) | high / business_description | included |
| 풍원정밀 | 371950 | 동사는 1996년 금속박판가공기술을 통한 첨단 디스플레이 부품 제조 회사로 설립, 2022년 코스닥에 상장함. 지난 28년간 금속박판가공기술로  | ai_semiconductor_material_equipment: 증착 (high) | high / business_description | included |
| 제닉스로보틱스 | 381620 | 동사는 2010년 설립되어 2024년 코스닥에 상장하고, 2025년에 해외 자회사 ZENIX ROBOTICS를 설립함. 반도체, 디스플레이, 자 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 에코프로에이치엔 | 383310 | 동사는 2021년 에코프로의 환경사업부문 인적분할로 신설되어 코스닥 상장함. 반도체/디스플레이 클린룸 케미컬 필터, 미세먼지 저감 및 온실가스  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 씨엠티엑스 | 388210 | 동사는 2013년 설립되어 2024년 상호를 주식회사 씨엠티엑스로 변경하고, 2025년 코스닥시장에 상장함. 반도체 전공정 중 식각, 증착 공정 | ai_semiconductor_material_equipment: 식각, 증착, 전공정, 반도체 전공정 (h | high / business_description | included |
| 자람테크놀로지 | 389020 | 동사는 2000년 설립된 시스템반도체 설계 전문 팹리스 기업으로, 2023년 기술성장기업 특례로 코스닥에 상장함. 통신반도체, 광트랜시버, 기가 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 에스비비테크 | 389500 | 동사는 2000년 설립되어 베어링, 감속기 등 기계장치 구동 부품을 제조·판매하며 정밀 기계요소 분야에서 독자 기술력을 축적함. 순수 국내 기술 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 오픈엣지테크놀로지 | 394280 | 동사는 2017년 설립된 AI 반도체 설계 IP 전문기업으로, 2019년 캐나다 TSS 인수로 R&D 역량 강화함. 또한 일본 현지법인 설립으로 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 워트 | 396470 | 동사는 2004년 반도체 및 디스플레이 공정의 환경제어 시스템 전문기업으로 설립되어 2023년 코스닥시장에 상장하고 있음. 반도체 전공정 Pho | ai_semiconductor_material_equipment: HBM, 후공정, 전공정, 반도체 전공정  | high / business_description | included |
| 가온칩스 | 399720 | 동사는 2012년 설립된 시스템 반도체 설계 전문 기업으로, 삼성 파운드리의 공식 디자인 솔루션 파트너(DSP) 및 Arm Approved De | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 그린리소스 | 402490 | 동사는 2023년 코스닥 상장 후 (주)위드엘씨를 합병하고, 반도체 및 디스플레이 공정 장비용 부품의 내식성·내플라즈마성 제고 소재 제조 및 코 | ai_semiconductor_material_equipment: 세정, PVD, 플라즈마, 반도체 (hig | high / business_description | included |
| HPSP | 403870 | 고압 수소 어닐링 장비 | 선단 공정·HBM 밸류체인. 5만 원대 중반 가격대. | high / existing_verified_data | included |
| 큐알티 | 405100 | 동사는 2014년 반도체 검사부문 분할로 설립되어 2022년 코스닥 상장한 반도체 및 전자부품 신뢰성 평가·분석 전문기업임. 모바일, 디스플레이 | ai_semiconductor_material_equipment: 반도체 검사, 반도체 (high) | high / business_description | included |
| 저스템 | 417840 | 동사는 2016년 설립 후 2022년 코스닥 상장을 승인받고 2023년 종속회사 플람을 인수했음. 반도체 제조 공정의 핵심인 N₂ Purge S | ai_semiconductor_material_equipment: 반도체 장비, 반도체 (high) | high / business_description | included |
| 라온텍 | 418420 | 동사는 2009년 설립된 국내 최초 마이크로디스플레이 솔루션 제공 기업으로, 2023년 코스닥에 기술성장기업으로 상장함. XR 기기용 스마트안경 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 제이오 | 418550 | 동사는 1994년 설립되어 2023년 코스닥에 상장한 첨단 나노소재 및 플랜트엔지니어링 전문기업임. 20여년간 이차전지 도전재용 탄소나노튜브를  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 기가비스 | 420770 | 동사는 2004년 설립된 반도체 기판 자동광학검사기 및 광학수리기를 제작·판매하는 글로벌 장비 업체로, 2023년 코스닥시장에 상장함. 2023 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 마이크로투나노 | 424980 | 동사는 2000년 설립되어 2023년 코스닥에 상장한 MEMS 기술 기반 반도체 테스트용 프로브카드 및 파운드리 서비스 전문기업임. 2025년까 | ai_semiconductor_material_equipment: HBM, 반도체, 테스트, 파운드리 (hi | high / business_description | included |
| 티에프이 | 425420 | 동사는 2003년 설립된 반도체 테스트 공정 전문기업으로 2022년 코스닥 상장함. Final Test, 신뢰성 테스트, SLT, SET 모사  | ai_semiconductor_material_equipment: 반도체, 테스트 (medium) | medium / business_description | included |
| 시지트로닉스 | 429270 | 동사는 2012년 설립되어 실리콘 소재 기반 반도체 개발부터 생산까지 담당하는 기업임. ESD, Power, Sensor 등의 광·개별소자를 개 | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 퀄리타스반도체 | 432720 | 동사는 2017년 초고속 인터커넥트 반도체 설계 기술을 바탕으로 설립되어 2023년 기술성장기업 특례로 코스닥시장에 상장함. 초고속 인터페이스  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 파두 | 440110 | 동사는 2015년 설립된 데이터센터 특화 시스템 반도체 팹리스 기업으로, 2023년 코스닥시장에 상장함. 클라우드, AI/Big data, 5G | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 에이직랜드 | 445090 | 동사는 2016년 설립된 시스템 반도체 디자인하우스로, 글로벌 1위 파운드리 TSMC의 국내 유일 공식 협력사임. 고객사의 반도체 회로 설계를  | ai_semiconductor_material_equipment: 반도체, 파운드리 (medium) | medium / business_description | included |
| 퓨릿 | 445180 | 동사는 2010년 산업용 및 디스플레이 공정 폐유기용제 회수·정제 사업으로 설립되어 2023년 코스닥 상장함. 초고순도 반도체용 케미컬과 디스플 | ai_semiconductor_material_equipment: 반도체용, 세정, 반도체 (high) | high / business_description | included |
| 큐리옥스바이오시스템즈 | 445680 | 동사는 2018년 설립되어 2023년 코스닥시장에 상장한 세포 분석 공정 자동화 장비 제조기업임. 세계 최초로 원심분리기 없이 세포 분석을 자동 | ai_semiconductor_material_equipment: 핸들러 (needs_review); ind | needs_review / business_description | needs_review |
| 아이엠티 | 451220 | 동사는 2000년 설립되어 레이저 및 건식 세정기술, 레이저 열처리 기술을 보유한 장비 개발·생산 전문기업임. 2025년 U-TECH VINA를 | ai_semiconductor_material_equipment: 세정, 건식, 반도체 (high) | high / business_description | included |
| 제이엔비 | 452160 | 동사는 2005년 설립되어 반도체 장비 및 LCD, 진공 시스템 제조·판매업을 영위하며, 2023년 코스닥시장에 상장함. stacker syst | ai_semiconductor_material_equipment: 반도체 장비, 진공펌프, 반도체 (high | high / business_description | included |
| 한빛레이저 | 452190 | 동사는 1997년 설립된 레이저 및 응용장비 제조 전문기업으로 코스닥에 상장함. 동사는 이차전지, 자동차, 반도체, 전자 등 핵심 산업에 레이저 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 사피엔반도체 | 452430 | 동사는 2017년 설립된 디스플레이 구동 시스템반도체 설계 전문 팹리스 기업으로, 2024년 기술성장기업 특례상장으로 코스닥시장에 상장함. Mi | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 아이씨티케이 | 456010 | 동사는 2017년 설립된 보안 시스템 반도체 설계 전문 회사로, 세계 최초로 PUF 기반 보안칩을 상용화하였으며, 2024년 코스닥에 상장함.  | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 한켐 | 457370 | 동사는 1999년 설립되어 2024년 코스닥 상장하였으며, OLED, 반도체 소재 등을 생산하는 전문기업으로 성장함. 동사는 고객사 요구에 맞춰 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 아이언디바이스 | 464500 | 동사는 2008년 혼성신호 SoC 반도체 기술로 설립되어 2024년 코스닥시장에 기술성장기업 특례상장함. 전력전자 기반 혼성신호 시스템반도체 설 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 링크솔루션 | 474650 | 동사는 2013년 설립되어 디지털 적층 성형기계 제조업을 영위하며, 2025년 코스닥시장에 기술성장기업으로 상장함. SLA, FDM, MBJ 방 | ai_semiconductor_material_equipment: 파운드리 (needs_review) | needs_review / business_description | needs_review |
| 마키나락스 | 477850 | 동사는 폐쇄망 등 특수한 환경에서 산업 특화 AI의 개발과 운영체계를 구축할 수 있는 독자 기술을 바탕으로 산업 현장의 문제를 해결하는 산업 특 | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 삼양엔씨켐 | 482630 | 동사는 2008년 설립된 반도체용 정밀화학 소재 전문 기업으로, 2025년 코스닥시장에 상장하였음. 반도체 제조 공정 중 노광 및 세정 공정에  | ai_semiconductor_material_equipment: 반도체용, 세정, 노광, 반도체 (high | high / business_description | included |
| 도우인시스 | 484120 | 동사는 2010년 초박형 강화유리(UTG) 연구개발, 제조 및 판매를 위해 설립되었고, 2019년 옥산 공장 준공 후 UTG를 세계 최초로 양산 | ai_semiconductor_material_equipment: 반도체용, 반도체 (high) | high / business_description | included |
| 노타 | 486990 | 동사는 2015년 설립된 온디바이스 AI 전문 기업으로, 2025년 코스닥시장에 기술성장기업 특례상장함. 자체 AI 최적화 플랫폼 NetsPre | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |
| 비츠로넥스텍 | 488900 | 동사는 2016년 비츠로테크의 특수사업부문 물적분할로 설립되어 2025년 코스닥시장에 기술성장기업 특례상장함. 한국형 우주발사체 누리호 엔진 컴 | ai_semiconductor_material_equipment: 플라즈마 (high); power_tech | needs_review / business_description | needs_review |
| 엘케이켐 | 489500 | 동사는 2007년 설립돼 2025년 코스닥 상장한 반도체 박막 증착 소재 전문기업임. 주력 제품으로 ALD용 High-k 소재(CP, PCP 리 | ai_semiconductor_material_equipment: 증착, 반도체 (high) | high / business_description | included |
| 세미파이브 | 490470 | 동사는 2019년 설립된 시스템 반도체 설계 전문기업으로, 2025년 12월 코스닥시장에 이익미실현기업 특례상장함. 2025년 중 SEMIFIV | ai_semiconductor_material_equipment: 반도체 (needs_review) | needs_review / business_description | needs_review |

## 전력기술

| 종목명 | 코드 | 사업내용 요약 | 포함 이유 | 근거 수준 | 검토 상태 |
|--------|------|---------------|-----------|-----------|-----------|
| 덕양에너젠 | 0001A0 | 동사는 2020년 덕양에서 인적분할로 설립되었고, 2025년 민컴퍼니와 주식교환으로 종속회사 됨. 고도 정제공정을 통해 순도 99.99% 이상의 | power_technology: SMR (high) | high / business_description | included |
| 보성파워텍 | 006910 | 동사는 1970년 설립, 1994년 코스닥시장 상장한 전력기자재 전문 제조업체임. 국내 전력시장을 중심으로 송배전 자재 및 발전소, 변전소 철골 | power_technology: 변압기, 송배전, 송전, 배전 (high) | high / business_description | included |
| 대한광통신 | 010170 | 동사는 1974년 광섬유 및 광케이블 제조업체로 설립되어 1994년 코스닥 상장 후 미주 및 유럽 판매법인을 설립함. 국내 유일 광섬유-광케이블 | power_technology: 전력 케이블 (high) | high / business_description | included |
| 세명전기 | 017510 | 동사는 1962년 설립, 1984년 법인전환 후 1991년 코스닥시장 상장됨. 송배변전선로 금구류를 한국전력공사에 납품하고, 전철용 금구류를 철 | power_technology: 송전, HVDC (high) | high / business_description | included |
| KBI메탈 | 024840 | 동사는 1987년 설립, 1994년 코스닥 상장된 전장부품 제조기업임. 메탈사업부는 전선용 동ROD 제조로 33년간 중소전선업체 공급망을 구축  | power_technology: 발전기 (needs_review) | needs_review / business_description | needs_review |
| 우리기술 | 032820 | 동사는 1993년 설립된 제어계측 전문기업으로 2000년 코스닥 상장하였으며, 2024년 소각재 자원순환사업 목적법인 ㈜이엘씨를 공동설립해 지분 | power_technology: 원자력, 원전 (high) | high / business_description | included |
| 제룡전기 | 033100 | 동사는 1986년 설립되어 2011년 중전기 사업부문으로 재편하였으며, 1997년 코스닥시장에 상장함. 변압기, 개폐기, GIS 제조 및 판매를 | power_technology: 변압기, GIS, 중전기 (high) | high / business_description | included |
| 서희건설 | 035890 | 동사는 1982년 운송전문업체로 설립 후 1994년 건설업으로 전환, 1999년 코스닥에 상장함. 포스코 토건정비공사 및 다수 관급공사 수주로  | power_technology: 송전 (high) | high / business_description | included |
| 금화피에스시 | 036190 | 동사는 1981년 플랜트 전문건설 회사로 설립됐고, 1995년 민간기업 최초로 발전정비사업에 진출했으며, 2000년 코스닥에 상장됨. 발전정비사 | power_technology: 발전설비 (high) | high / business_description | included |
| 삼표시멘트 | 038500 | 동사는 1990년 설립하여 2001년 코스닥시장에 상장하였고, 2010년 동양시멘트 흡수합병 후 2017년 삼표시멘트로 변경함. 강원도 삼척시  | power_technology: 발전설비 (high) | high / business_description | included |
| 케이엘넷 | 039420 | 동사는 1994년 물류비 절감 통한 국가경쟁력 강화 목적 설립 후 2002년 코스닥에 상장함. 해운항만물류 중심으로 전자문서중계서비스(EDI)  | power_technology: GIS (high) | high / business_description | included |
| SG&G | 040610 | 동사는 1993년 설립, 2000년 코스닥 상장 및 2007년 네덱스 합병으로 물류업으로 업종을 변경하고 2020년 창원지점을 설치하여 자동차부 | power_technology: 원전 (high) | high / business_description | included |
| 오르비텍 | 046120 | 동사는 1991년 비파괴기술검사 목적으로 설립되어 2010년 코스닥시장에 상장하고, 2025년 파인테크닉스 지분 42.09% 취득으로 종속회사를 | power_technology: 원자력, 원전 (high) | high / business_description | included |
| 비츠로시스 | 054220 | 동사는 1989년 CLEMESSY와 기술협력으로 출범해 2000년 비츠로시스로 변경됐으며, 2025년 브이앤이를 편입함. 자동제어시스템 제조업체 | power_technology: 원자력, 원전, SMR (high) | high / business_description | included |
| 유신 | 054930 | 동사는 1966년 건설엔지니어링 사업을 목적으로 설립, 2002년 코스닥에 상장되었으며 2025년 씨이테크와의 합병으로 EPC부문을 확대함. 도 | power_technology: 원전 (high) | high / business_description | included |
| CNT85 | 056730 | 동사는 1996년 설립 후 2002년 코스닥에 상장하였고, 환경시설과 플랜트 설비의 설계·시공, 필터프레스 제조, 주택사업을 하는 중소기업임.  | power_technology: 발전설비 (high) | high / business_description | included |
| 캐스텍코리아 | 071850 | 동사는 1998년 전자제품 및 자동차 부품을 주물공정을 통해 생산하는 것을 목적으로 설립되었으며, 소주과태과기유한공사 등 3개의 종속기업을 보유 | power_technology: 터빈 (needs_review) | needs_review / business_description | needs_review |
| 에이치시티 | 072990 | 동사는 2000년 현대전자산업 품질보증부문 분리로 설립되고 2016년 코스닥에 상장함. 시험인증서비스와 측정기기 교정용역을 주사업으로 하며 정보 | power_technology: 원전 (high) | high / business_description | included |
| 일진파워 | 094820 | 동사는 1990년 설립되어 2014년 화공 및 플랜트 사업을 분리하고, 연료전지발전소 건설을 위해 진천그린에너지와 고양그린에너지를 신설함. 발전 | power_technology: 원자력 (high) | high / business_description | included |
| 신화프리텍 | 095190 | 동사는 2003년 공작기계제조업을 목적으로 설립되었고, 2005년 동우정밀 인수 및 2007년 코스닥 상장됨. 방산·항공 부문에서 K-2, K- | power_technology: 발전설비 (high) | high / business_description | included |
| 한국정밀기계 | 101680 | 동사는 1998년 설립되어 공작기계 및 산업기계 제조·판매를 주력으로 하고, 2009년 코스닥에 상장함. 금속 공작물을 가공해 원하는 형상을 만 | power_technology: 발전설비 (high); industrial_robot_equipment: 공 | needs_review / business_description | needs_review |
| 티씨머티리얼즈 | 125020 | 동사는 1995년 설립되어 전력인프라, 전장, 가전 소재 및 모터 관련 제품과 서비스를 생산하는 기업임. 전도성과 경제성 뛰어난 구리를 활용해  | power_technology: 배전, 전력기기, 발전기 (high) | high / business_description | included |
| 비나텍 | 126340 | 동사는 1999년 설립된 친환경 에너지 기업으로, 슈퍼커패시터와 수소연료전지 핵심 소재 및 부품을 연구·개발·양산하고 있음. 슈퍼커패시터 셀 및 | power_technology: 전력망 (high) | high / business_description | included |
| 카티스 | 140430 | 동사는 2006년 설립된 공간인지 보안플랫폼 기업으로, 2024년 코스닥에 상장함. 보안공간과 이동체의 상태정보를 처리하는 플랫폼을 개발하고,  | power_technology: 원자력 (high) | high / business_description | included |
| 제룡산업 | 147830 | 동사는 2011년 제룡전기㈜로부터 인적분할되어 설립되고, 2012년 코스닥에 상장함. 송전·배전·지중선 관련 전기기자재와 통신기자재, 철도자재  | power_technology: 송전, 배전 (high) | high / business_description | included |
| 서전기전 | 189860 | 동사는 1988년 설립된 수배전반 제조 및 판매를 영위하는 전력변환기기 전문기업임. 발전소에서 생산된 전력이 송변전계통을 거쳐 최종 소비자에게  | power_technology: 배전, 전력변환, 전력기기, 배전반 (high) | high / business_description | included |
| 제일일렉트릭 | 199820 | 동사는 1980년 설립되어 배선기구와 분전반 등을 제조하며 2020년 코스닥시장에 상장됨. 종속법인인 쟈베스코리아전자와 JABEZ VINA CO | power_technology: 차단기 (high) | high / business_description | included |
| 솔디펜스 | 215090 | 동사는 1999년 설립되어 코스닥시장에 상장하였으며, 2025년 솔디펜스로 상호변경함. 유도무기 및 항공전자 부품을 개발·생산하여 군에 납품하고 | power_technology: 원자력, 터빈, 발전기 (high) | high / business_description | included |
| 피앤씨테크 | 237750 | 동사는 1999년 전력계통 디지털전력기기 생산을 목적으로 설립되어 2016년 코스닥시장에 상장함. 배전자동화 단말장치, 디지털보호계전기, 원격감 | power_technology: 배전, 계전, 전력기기 (high) | high / business_description | included |
| 케일럼 | 258610 | 동사는 2009년 설립되어 2017년 코스닥에 상장하고, 2022년 주식회사 케일럼으로 상호를 변경했음. 지열발전설비 및 화공/LNG플랜트 기자 | power_technology: 발전설비 (high) | high / business_description | included |
| 이지스 | 261520 | 동사는 2001년 설립된 국내 3차원 GIS 및 디지털 트윈 기술 선도 기업으로, 2025년 코스닥시장에 기술성장기업 특례상장함. 공간정보 출판 | power_technology: GIS (high) | high / business_description | included |
| 영화테크 | 265560 | 동사는 2000년 설립되어 자동차용 정션박스, 전기차, 전력전자부품 등을 개발하여 국내외 자동차 OEM사에 공급하고 있음. 정션박스, 전기차 및 | power_technology: 전력변환 (high) | high / business_description | included |
| 와이엠텍 | 273640 | 동사는 2004년 설립하고 2021년 코스닥에 상장된 직류 전력제어용 릴레이 전문 제조기업임. 에너지저장장치, 전기차 충전기 등 다양한 분야에  | power_technology: 차단기, 전력제어 (high) | high / business_description | included |
| 서남 | 294630 | 동사는 2004년 설립, 2020년 코스닥 상장한 중소기업으로, 2세대 고온초전도 선재 제조 및 판매를 주력으로 함. 독자기술 RCE-DR 공정 | power_technology: 전력케이블, 발전기 (high) | high / business_description | included |
| 웨이버스 | 336060 | 동사는 2004년 설립된 공간정보 통합 솔루션 기업으로, 2022년 코스닥 상장 후 네이버시스템즈 GIS사업부문 양수로 공간정보 원천데이터 생산 | power_technology: GIS (high) | high / business_description | included |
| 위드텍 | 348350 | 동사는 2003년 환경산업 분야의 고감도 정밀측정과 오염제어 기술 개발을 목적으로 설립되었으며, 2020년 코스닥시장에 상장함. 반도체·디스플레 | ai_semiconductor_material_equipment: 반도체 (needs_review); pow | needs_review / business_description | needs_review |
| 코스텍시스 | 355150 | 동사는 2013년 설립되어 반도체 패키징용 방열 소재 및 부품을 개발·생산하며, 2023년 코스닥시장에 상장함. RF 통신 패키지, 전력 반도체 | ai_semiconductor_material_equipment: 반도체용, 반도체 패키징, 반도체, 패키징 | needs_review / business_description | needs_review |
| 이지트로닉스 | 377330 | 동사는 2008년 전력변환장치 제조·판매를 목적으로 설립되었으며, 2023년 타법인 지분투자 및 미국 법인 설립을 완료함. 전기·수소차용, 방산 | power_technology: 배전, 전력변환 (high) | high / business_description | included |
| LS머트리얼즈 | 417200 | 동사는 2021년 LS엠트론 울트라캐패시터 사업부문 물적분할로 설립되었음. 신재생에너지, 스마트팩토리 AGV, 전기차 분야 중대형 울트라캐패시터 | power_technology: 전력망 (high) | high / business_description | included |
| 우진엔텍 | 457550 | 동사는 2013년 원자력 및 화력발전소 계측제어설비 정비 사업을 시작해 2024년 코스닥시장에 상장한 중소기업임. 동사는 설비 진단 및 성능개선 | power_technology: 원자력, 원전 (high) | high / business_description | included |
| 모티브링크 | 463480 | 동사는 1977년 전압·전류 제어 변압기 전문업체로 설립되어, 가전용 부품에서 자동차 부품 공급업체로 변모하며 2025년 코스닥에 상장함. 전장 | power_technology: 변압기 (high) | high / business_description | included |
| 비츠로넥스텍 | 488900 | 동사는 2016년 비츠로테크의 특수사업부문 물적분할로 설립되어 2025년 코스닥시장에 기술성장기업 특례상장함. 한국형 우주발사체 누리호 엔진 컴 | ai_semiconductor_material_equipment: 플라즈마 (high); power_tech | needs_review / business_description | needs_review |

## 산업·로봇 장비

| 종목명 | 코드 | 사업내용 요약 | 포함 이유 | 근거 수준 | 검토 상태 |
|--------|------|---------------|-----------|-----------|-----------|
| 엔비알모션 | 0004V0 | 동사는 2026년 코스닥에 기술성장기업으로 상장했으며, 종속법인으로 엔비알롤러를 보유하고 있음. 차량, 산업용 기계, 로봇 등의 다양한 어플리케 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 피제이전자 | 006140 | 동사는 1969년 설립된 EMS 사업 전문기업으로, 1993년 코스닥 상장하였으며 Total 제조 System을 갖춘 선도적 EMS 서비스 회사 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 유진기업 | 023410 | 동사는 1984년 설립, 1994년 코스닥 상장 후 레미콘 제조·판매를 주력으로 수도권에 공장 운영하고 있음. 주요 종속회사로 골프장 운영 동화 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 세원물산 | 024830 | 동사는 1985년 설립되어 1994년 코스닥에 상장하였고, 경북 영천시에 본사와 공장을 두고 있음. 현대자동차와 거래하며 여러 차종에 자동차 차 | industrial_robot_equipment: 자동화 설비 (high) | high / business_description | included |
| 모아텍 | 033200 | 동사는 1989년 설립, 1997년 코스닥 상장한 소형정밀모터 제조업체임. 가전, 사무기기, 자동차, 통신 분야의 STEPPING MOTOR 제 | industrial_robot_equipment: 정밀모터 (high) | high / business_description | included |
| 재영솔루텍 | 049630 | 동사는 1984년 설립하고 2003년 코스닥에 상장한 카메라 액추에이터 전문기업으로, 베트남 생산법인인 재영VINA를 보유하고 있음. 스마트폰  | industrial_robot_equipment: 액추에이터 (needs_review) | needs_review / business_description | needs_review |
| 유진로봇 | 056080 | 동사는 2001년 코스닥 상장한 자율주행 물류로봇 및 스마트 자동화 장비 전문기업임. 자율주행 물류로봇 고카트, 3D 라이다 센서, 로봇자동화  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 에스피지 | 058610 | 정밀 제어용 모터·감속기 | 로봇 부품 국산화 핵심. | high / existing_verified_data | included |
| 해성에어로보틱스 | 059270 | 동사는 1997년 감속기 전문 제조기업으로 설립되어 2021년 코스닥시장에 상장함. 승강기용 권상기를 주력으로 생산하며, Worm Gear 독자 | industrial_robot_equipment: 감속기, 로봇 (high) | high / business_description | included |
| 제이케이시냅스 | 060230 | 동사는 1999년 설립되어 화공약품 및 전자부품을 제조하며, 2025년 소니드디앤디와 셀렉터를 취득해 사업 영역을 확장함. 전자소재 개발, RF | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 큐렉소 | 060280 | 동사는 1992년 설립, 2002년 코스닥에 상장한 의료로봇 전문기업임. 의료로봇사업부 정형외과 수술로봇 큐비스-조인트, 큐비스-스파인, 재활치 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| KH바텍 | 060720 | 동사는 1992년 비철금속 소형정밀 다이캐스팅 전문기업으로 설립되어 2002년 코스닥 상장 후 8개 비상장 종속회사를 보유하고 있음. 스마트폰· | industrial_robot_equipment: CNC, 로봇 부품, 로봇 (high) | high / business_description | included |
| 엑시온그룹 | 069920 | 동사는 2000년 SK글로벌 신규사업부로 시작, 2001년 (주)위즈위드코리아로 독립, 2007년 코스닥 상장, 2024년 엑시온그룹으로 상호  | industrial_robot_equipment: 산업용 로봇, 로봇 (high) | high / business_description | included |
| 가온그룹 | 078890 | 동사는 2001년 설립, 2005년 코스닥 상장, 2023년 가온그룹 주식회사로 변경함. 세계 전역 AI 솔루션, OTT, 네트워크 디바이스,  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 케스피온 | 079190 | 동사는 1998년 설립되어 2005년 코스닥에 상장하였으며, 베트남 현지법인 2개와 (주)케스피온컴텍 등 3개 계열사를 보유함. 이동통신용 안테 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 이엠앤아이 | 083470 | 동사는 1999년 설립되었고, 2008년 코스닥 상장 후 2020년 ㈜이엠인덱스를 합병해 주식회사 이엠앤아이로 사명을 변경함. OLED 소재의  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 동우팜투테이블 | 088910 | 동사는 1993년 축산물 제조 및 판매를 목적으로 설립되었고 2006년 코스닥에 상장되었으며, 우농 등 계열사를 보유하고 있음. 농림수산식품부  | industrial_robot_equipment: FA (needs_review) | needs_review / business_description | needs_review |
| 넥스턴앤롤코리아 | 089140 | 동사는 2000년 CNC자동선반 제조 및 판매를 목표로 설립되어 2006년 코스닥에 상장했으며, 2025년 (주)넥스턴앤롤코리아로 상호 변경함. | industrial_robot_equipment: CNC, 자동화 설비, 로봇 (high) | high / business_description | included |
| 휴림로봇 | 090710 | 동사는 1999년 산업용 및 지능형 로봇 생산을 목적으로 설립되어 2006년 코스닥에 상장하였으며, 5개 종속회사를 보유함. 산업용과 지능형 로 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 푸른기술 | 094940 | 동사는 1997년 설립되어 2007년 코스닥 상장 후 금융자동화, 역무자동화, 협동로봇 제조 및 판매를 영위하고 있음. 금융자동화 부문에서 보급 | industrial_robot_equipment: 협동로봇, 로봇 (high) | high / business_description | included |
| 제이엠티 | 094970 | 동사는 1998년 설립되어 2007년 코스닥에 상장하고, 2023년에 제이엠아이(주)와 종속회사를 연결대상으로 편입함. 전자부품 제조 전문 EM | industrial_robot_equipment: 자동화 설비 (high) | high / business_description | included |
| 스맥 | 099440 | 공작기계·산업용 로봇 자동화 | 로봇 공정 자동화. 산업 자동화 테마. | high / existing_verified_data | included |
| 서암기계공업 | 100660 | 동사는 1978년 공작기계용 기어 제조를 목적으로 설립됐고, 2011년 코스닥시장에 상장됨. 화천기계, 화천기공과 함께 화천그룹을 형성하고 있음 | industrial_robot_equipment: 공작기계 (high) | high / business_description | included |
| 모베이스 | 101330 | 동사는 1999년 금형 제작 및 판매를 목적으로 설립되어 2019년 코스닥 상장 자동차 전장부품 기업인 (주)모베이스전자를 인수하여 자동차 전장 | industrial_robot_equipment: 공정 자동화 (high) | high / business_description | included |
| 한국정밀기계 | 101680 | 동사는 1998년 설립되어 공작기계 및 산업기계 제조·판매를 주력으로 하고, 2009년 코스닥에 상장함. 금속 공작물을 가공해 원하는 형상을 만 | power_technology: 발전설비 (high); industrial_robot_equipment: 공 | needs_review / business_description | needs_review |
| 톱텍 | 108230 | 동사는 1996년 설립 후 2009년 코스닥에 상장, 4개 계열회사 보유함. 배터리 셀 모듈화 설비의 FA사업과 전기차 모터 자동화 설비의 모빌 | industrial_robot_equipment: 자동화 설비, 로봇, FA (high) | high / business_description | included |
| 로보티즈 | 108490 | 동사는 1999년 설립된 로봇 전문기업으로, 액츄에이터와 감속기 등 핵심 기술을 바탕으로 로봇을 개발하고 제조함. 액츄에이터는 로봇의 관절 역할 | industrial_robot_equipment: 감속기, 로봇 (high) | high / business_description | included |
| 씨싸이트 | 109670 | 동사는 1999년 설립된 의류 제조 전문기업으로 OEM 및 ODM 방식으로 니트 의류를 생산하고, 2023년 코스닥시장에 상장함. 동사는 미국  | industrial_robot_equipment: 공정 자동화 (high) | high / business_description | included |
| 알엔티엑스 | 123010 | 동사는 2003년 이미지센서 패키징 분야 특허기술로 설립되어 2016년 코스닥에 상장된 기술성장기업임. 이미지센서 패키징을 주력으로 하며 자동차 | ai_semiconductor_material_equipment: 패키징, 테스트 (medium); indu | needs_review / business_description | needs_review |
| 한라캐스트 | 125490 | 동사는 2005년 설립되어 알루미늄 등 소재를 적용한 부품제조를 하며, 2025년 코스닥시장에 상장함. LG전자 등 대기업을 1차 고객사로 두고 | industrial_robot_equipment: 로봇 부품, 로봇 (high) | high / business_description | included |
| 티피씨글로벌 | 130740 | 동사는 1998년 자동차부품 제조를 목적으로 설립, 2011년 코스닥에 상장, 연결종속회사로 해성에어로보틱스와 고리를 보유함. 자동차부품부문은  | industrial_robot_equipment: 감속기, 로봇 (high) | high / business_description | included |
| 넥스트아이 | 137940 | 동사는 1998년 산업처리 자동측정 및 제어장비 제조를 목적으로 설립돼 2011년 코스닥에 상장함. 머신비전 기술을 활용한 LCD 외관검사장비  | industrial_robot_equipment: 머신비전 (needs_review) | needs_review / business_description | needs_review |
| 앤로보틱스 | 138360 | 동사는 2001년 설립되어 2013년 코스닥시장에 상장한 식품가공 설비 전문기업임. 장비를 국산화하여 전처리부터 멸균까지 식품가공 전 과정의 다 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 파수AI | 150900 | 동사는 2000년 설립, 2013년 코스닥 상장한 지식정보보안 기업으로, 2016년 에스피에이스 인수로 정보보호컨설팅을 확장하고 2018년 애플 | industrial_robot_equipment: FA (needs_review) | needs_review / business_description | needs_review |
| 하이젠알앤엠 | 160190 | 동사는 2007년 설립 후 오티스엘리베이터코리아의 산업용 모터사업부 인수로 시작함. 중국 청도 공장 인수로 가격 경쟁력과 본사 기술력을 결합한  | industrial_robot_equipment: 서보모터, 로봇, 액추에이터 (high) | high / business_description | included |
| 오늘이엔엠 | 192410 | 동사는 1997년 전자통신 제조 및 서비스를 목적으로 설립되었으며, 2025년 휴림네트웍스에서 오늘이엔엠으로 상호를 변경함. 안테나 사업부문은  | industrial_robot_equipment: 로봇 부품, 로봇 (high) | high / business_description | included |
| 디에이테크놀로지 | 196490 | 동사는 2000년 설립되어 이차전지 생산 자동화설비 제조 및 판매업을 영위하는 중소기업임. 이차전지 생산공정 중 조립, 활성화 공정 장비를 제작 | industrial_robot_equipment: 자동화 설비 (high) | high / business_description | included |
| 케이엔알시스템 | 199430 | 동사는 2000년 설립되어 2024년 코스닥 기술성장기업으로 상장함. 시험장비사업은 맞춤형 시뮬레이터급 장비 설계·제작으로 자동차 등 다양한 포 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 아크솔루션스 | 203690 | 동사는 2005년 단백질 제품 연구개발 및 화장품 판매 목적으로 설립되어 2015년 코스닥 상장, 2024년 아크솔루션스로 사명 변경함. 물티슈 | industrial_robot_equipment: 자동화 설비 (high) | high / business_description | included |
| 와이제이링크 | 209640 | 동사는 2009년 설립되어 2024년 코스닥시장에 상장하고, 태국법인 설립으로 PCB어셈블리 제조 및 판매 사업을 확장함. 스마트화를 위한 SM | ai_semiconductor_material_equipment: 후공정 (high); industrial_ | needs_review / business_description | needs_review |
| 로보로보 | 215100 | 동사는 2000년 청소 및 보안 로봇 전문 개발로 시작해 2005년 교육용 로봇 개발에 뛰어들었고, 2017년 기업인수목적회사와 합병을 완료했음 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 폴라리스세원 | 234100 | 동사는 1992년 자동차 공조부품 제조업체로 설립되었으며, 2025년 핸디소프트를 종속회사로 편입하여 사업을 확장함. 자동차 공조부품, 합성사  | industrial_robot_equipment: 공정자동화 (high) | high / business_description | included |
| 야스 | 255440 | 동사는 2002년 설립, 2017년 코스닥 상장하고 Fab1~3 공장을 보유하며 8.6세대 제조 위한 Fab4 가동 준비 중임. OLED 디스플 | ai_semiconductor_material_equipment: 증착 (high); industrial_r | needs_review / business_description | needs_review |
| 에브리봇 | 270660 | 동사는 2015년 설립되어 자율주행 기술 기반 로봇청소기 사업을 영위하며 2021년 코스닥 상장함. 2016년 세계 최초 듀얼스핀 방식 물걸레  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 레인보우로보틱스 | 277810 | 동사는 2011년 KAIST 연구원들이 창업한 벤처로, 한국 최초 인간형 이족보행 로봇 'HUBO'가 회사의 근간임. 협동로봇, 초정밀지향마운트 | industrial_robot_equipment: 협동로봇, 로봇 (high) | high / business_description | included |
| 라온피플 | 300120 | 동사는 2010년 설립된 AI 기반 비전솔루션 전문기업이며, 2023년 (주)티디지 지분 인수를 통해 종속회사 3개를 보유하고 있음. AI 머신 | industrial_robot_equipment: 머신비전 (needs_review) | needs_review / business_description | needs_review |
| 아이엘 | 307180 | 동사는 2008년 고효율 LED 조명 및 관련 제품 개발을 목적으로 설립되어 2019년 스팩 합병을 통해 코스닥시장에 상장함. 2024년 아이엘 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 딥노이드 | 315640 | 동사는 2008년 설립된 인공지능 전문 기업으로, 2021년 코스닥시장에 상장하였음. 의료 진단·판독 보조 및 조기진단을 위한 DEEP:NEUR | industrial_robot_equipment: 머신비전 (needs_review) | needs_review / business_description | needs_review |
| 에스피시스템스 | 317830 | 동사는 1988년 설립되어 로봇자동화 제조 시스템 구축, 산업기계와 자동차 부품, 소프트웨어 제조/판매 등을 주요 사업으로 하고 있음. 당기 중 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| LS티라유텍 | 322180 | 동사는 2006년 설립하여 2019년 코스닥 상장했으며, 2024년 LS일렉트릭으로 최대주주가 변경되며 전력/자동화 분야로 사업 확장 중임. 무 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 포커스에이아이 | 331380 | 동사는 2012년 물리보안솔루션 개발 및 판매사업을 위해 설립되었고, 2021년 유진기업인수목적5호와 합병을 완료함. AI 카메라, 영상저장장치 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 세림B&G | 340440 | 동사는 2003년 설립되어 2021년 코스닥 상장된 친환경 포장재 및 로보틱스 전문기업임. 진공성형 기술 기반 식품 포장용 플라스틱 용기와 생분 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 시선AI | 340810 | 동사는 2010년 설립 후, 2025년 물적분할로 로봇 부문 자회사 유온로보틱스를 신설하고 솔크홀딩스와 대보DX를 자회사로 편입함. Vision | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 엠엑스온 | 347890 | 동사는 1999년 설립된 디지털 전환 전문 기업으로 에스엠코어 지분을 취득하여 종속회사로 편입함. 스마트HMI, 스마트SCADA 및 솔루션을 제 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 뉴로메카 | 348340 | 동사는 2013년 설립되어 2022년 코스닥 상장한 로봇 개발·생산·판매 및 자동화솔루션 공급 기업임. 협동로봇과 자동화솔루션, EtherCAT | industrial_robot_equipment: 협동로봇, 로봇, 액추에이터 (high) | high / business_description | included |
| 아모센스 | 357580 | 동사는 2008년 설립되어 2021년 코스닥에 상장함. 2025년 자회사 아모에스넷 지분 취득으로 연결대상 종속회사를 보유하게 됨. 동사는 무선 | industrial_robot_equipment: 로봇, 산업 자동화 (medium) | medium / business_description | included |
| 엠아이큐브솔루션 | 373170 | 동사는 2005년 설립된 제조현장 정보 통합 소프트웨어 전문기업으로 2023년 코스닥 상장함. 다양한 업종 대상으로 Smart Factory 솔 | industrial_robot_equipment: FA (needs_review) | needs_review / business_description | needs_review |
| 마음AI | 377480 | 동사는 2014년 설립되어 2021년 코스닥에 상장, 인공지능 기술 기반 Agent AI와 Physical AI 사업을 함. Agent AI는  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 유일로보틱스 | 388720 | 동사는 2011년 산업용 로봇 및 자동화시스템 전문기업으로 설립되어, 2022년 코스닥시장에 상장함. 직교로봇, 다관절로봇, 협동로봇 등 산업용 | industrial_robot_equipment: 산업용 로봇, 협동로봇, 직교로봇, 로봇 (high) | high / business_description | included |
| 에이프릴바이오 | 397030 | 동사는 2013년 교원창업으로 설립된 연구개발 중심기업으로, 2022년 코스닥시장에 특례상장함. HuDVFab 라이브러리와 SAFA 플랫폼으로  | industrial_robot_equipment: FA (needs_review) | needs_review / business_description | needs_review |
| 모델솔루션 | 417970 | 동사는 2005년 법인 전환 후 2022년 코스닥시장에 상장하였으며, 자동차, 항공우주, IT/통신, 의료기기 등 고부가가치 산업의 프로토타입  | industrial_robot_equipment: CNC, FA (high) | high / business_description | included |
| 케이엔에스 | 432470 | 동사는 2006년 설립되어 2023년 코스닥 상장함. 2025년 은성에프에이 지분 취득을 통해 종속회사 확대함. 원통형 배터리 CID 장비 및  | industrial_robot_equipment: 자동화 설비, 로봇 (high) | high / business_description | included |
| 코스모로보틱스 | 439960 | 동사의 명칭은 "코스모로보틱스 주식회사"이며, 영문으로는 COSMO ROBOTICS CO., Ltd. 로 표기함. 성인용 하지 외골격 보행보조  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 큐리옥스바이오시스템즈 | 445680 | 동사는 2018년 설립되어 2023년 코스닥시장에 상장한 세포 분석 공정 자동화 장비 제조기업임. 세계 최초로 원심분리기 없이 세포 분석을 자동 | ai_semiconductor_material_equipment: 핸들러 (needs_review); ind | needs_review / business_description | needs_review |
| 엔젤로보틱스 | 455900 | 동사는 2017년 설립된 지능형 웨어러블 로봇 연구개발 및 판매 기업으로, 2024년 코스닥시장에 상장함. 보행치료용 angel MEDI, 산업 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 나우로보틱스 | 459510 | 동사는 2016년 설립되어 산업용 로봇 및 자율주행 물류로봇, 로봇 자동화 시스템을 개발·제조·공급하며, 2025년 코스닥 기술성장기업으로 상장 | industrial_robot_equipment: 산업용 로봇, 직교로봇, 스카라, 로봇 (high) | high / business_description | included |
| 알트 | 459550 | 동사는 2017년 설립되었으며 2025년 코스닥에 상장한 스마트 디바이스 개발 제조 기업임. 모바일 부문에서 키즈폰과 시니어폰을 통신 3사에,  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 피앤에스로보틱스 | 460940 | 동사는 2024년 코스닥 상장과 2025년 멕시코 법인을 설립했으며, 국내 연구단체와 휴머노이드 로봇 등 첨단 제품을 설계하며 기술을 내재화함. | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 클로봇 | 466100 | 동사는 2013년 설립되어 2024년 코스닥시장에 기술성장기업으로 상장하였으며, 범용 자율주행 솔루션 CHAMELEON과 로봇 관제 솔루션 CR | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 사이냅소프트 | 466410 | 동사는 2000년 설립하여 2024년 코스닥시장에 상장함. 기업시장과 공공 및 교육시장을 대상으로 AI와 디지털 전환을 통해 비즈니스 혁신과 고 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 씨메스로보틱스 | 475400 | 동사는 2014년 3차원 비전기술, AI기술, 로봇 제어기술을 기반으로 설립되어 2024년 코스닥상장한 AI Robotics 기업임. 지능형 로 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 에이럭스 | 475580 | 동사는 2015년 설립된 로봇 및 드론 제조기업으로 2020년 지에듀와 2025년 이알 인수 등으로 생산능력을 확대했음. 교육용 드론 및 로봇  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 티엑스알로보틱스 | 484810 | 동사는 2017년 설립된 물류 및 로봇 자동화 전문기업으로 2024년 자회사 로탈을 흡수합병하고 2025년 코스닥에 상장함. 물류자동화 부문은  | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
| 리브스메드 | 491000 | 동사는 2011년 최소침습수술용 복강경 수술기구 개발을 목표로 설립되었으며, 2025년 코스닥시장에 기술성장기업 특례상장함. 독자적 다관절 기술 | industrial_robot_equipment: 로봇 (needs_review) | needs_review / business_description | needs_review |
