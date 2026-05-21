"""MVP 4 — 관심 섹터 신규 후보군 (watchlist·대형주 제외용 확장 유니버스)."""

from __future__ import annotations

from typing import Any, Iterator

from data.kr_watchlist import watchlist_ticker_set

# Slack·스캔 기본 제외 대형 대표주 (candidate_scanner와 동일 목록)
EXCLUDED_LARGE_CAPS: frozenset[str] = frozenset(
    {
        "005930",  # 삼성전자
        "000660",  # SK하이닉스
        "009150",  # 삼성전기
        "011070",  # LG이노텍
        "267260",  # HD현대일렉트릭
        "298040",  # 효성중공업
    }
)

# 우선주 티커 (풀에서 제거·자동 제외)
KNOWN_PREFERRED_TICKERS: frozenset[str] = frozenset(
    {
        "103595",  # 일진전기우
        "009155",  # 삼성전기우 (있을 경우)
    }
)

# 종목명이 '우'로 끝나도 보통주인 예외 (오탐 방지)
_PREFERRED_NAME_FALSE_POSITIVES: frozenset[str] = frozenset(
    {
        "대우",
    }
)

# (sector_name, name, ticker) — 중복 티커는 첫 항목만 유지
_CANDIDATE_POOL: tuple[tuple[str, str, str], ...] = (
    # ── 반도체 소재 ──
    ("반도체 소재", "솔브레인", "357780"),
    ("반도체 소재", "후성", "093370"),
    ("반도체 소재", "SK아이이테크놀로지", "361610"),
    ("반도체 소재", "덕산네오룩스", "213420"),
    ("반도체 소재", "이엔에프테크놀로지", "102710"),
    ("반도체 소재", "SKC", "011790"),
    ("반도체 소재", "LX세미콘", "108320"),
    ("반도체 소재", "파미셀", "005690"),
    ("반도체 소재", "명인화학", "012690"),
    ("반도체 소재", "솔브레인홀딩스", "036830"),
    ("반도체 소재", "파트론", "091700"),
    ("반도체 소재", "원익QNC", "030530"),
    ("반도체 소재", "KPX케미칼", "025000"),
    ("반도체 소재", "휴먼텍", "200670"),
    ("반도체 소재", "아이앤씨", "052860"),
    ("반도체 소재", "미래나노텍", "095500"),
    ("반도체 소재", "코오롱인더", "120110"),
    # ── 반도체 장비 ──
    ("반도체 장비", "HPSP", "403870"),
    ("반도체 장비", "원익IPS", "240810"),
    ("반도체 장비", "리노공업", "058470"),
    ("반도체 장비", "GST", "083450"),
    ("반도체 장비", "케이씨텍", "281820"),
    ("반도체 장비", "레이크머티리얼즈", "281740"),
    ("반도체 장비", "파크시스템스", "140860"),
    ("반도체 장비", "SFA반도체", "036540"),
    ("반도체 장비", "코세스", "089890"),
    ("반도체 장비", "에이디테크", "200710"),
    ("반도체 장비", "유니테스트", "088390"),
    ("반도체 장비", "한미반도체", "042700"),
    ("반도체 장비", "티에스이", "131290"),
    ("반도체 장비", "지니틱스", "303030"),
    ("반도체 장비", "엘컴텍", "097520"),
    ("반도체 장비", "우리이앤엘", "153490"),
    ("반도체 장비", "고영", "098460"),
    ("반도체 장비", "에스앤에스텍", "101490"),
    ("반도체 장비", "오로스테크놀로지", "322310"),
    ("반도체 장비", "에스엠코리아", "041510"),
    ("반도체 장비", "웹스", "196700"),
    ("반도체 장비", "엘앤씨", "066670"),
    ("반도체 장비", "제주반도체", "080220"),
    ("반도체 장비", "아이엠티", "139130"),
    # ── 반도체 부품 ──
    ("반도체 부품", "이수페타시스", "007660"),
    ("반도체 부품", "대덕", "008060"),
    ("반도체 부품", "심텍홀딩스", "036710"),
    ("반도체 부품", "이수화학", "005950"),
    ("반도체 부품", "하나마이크론", "067310"),
    ("반도체 부품", "텔레칩스", "054450"),
    ("반도체 부품", "LX하우시스", "108670"),
    ("반도체 부품", "서울반도체", "046890"),
    ("반도체 부품", "알에프텍", "061040"),
    ("반도체 부품", "코아시아", "045970"),
    ("반도체 부품", "피에이치에이", "057880"),
    ("반도체 부품", "PI첨단소재", "178920"),
    ("반도체 부품", "칩스앤미디어", "094360"),
    ("반도체 부품", "HL홀딩스", "060980"),
    # ── PCB/기판 ──
    ("PCB/기판", "하나마이크론", "067310"),
    ("PCB/기판", "신원", "092870"),
    ("PCB/기판", "크리스탈신소재", "114190"),
    ("PCB/기판", "필옵틱스", "161580"),
    ("PCB/기판", "TPC", "051370"),
    ("PCB/기판", "HD현대코퍼레이션", "136490"),
    ("PCB/기판", "엠에스오토텍", "123040"),
    ("PCB/기판", "웨이비스", "194700"),
    ("PCB/기판", "이수페타시스", "007660"),
    ("PCB/기판", "대덕", "008060"),
    ("PCB/기판", "인탑스", "049070"),
    ("PCB/기판", "로체시스템즈", "071280"),
    ("PCB/기판", "케이엠더블유", "032500"),
    ("PCB/기판", "유라클", "088340"),
    ("PCB/기판", "유비쿼스", "264450"),
    # ── HBM/후공정 ──
    ("HBM/후공정", "실리콘투", "257720"),
    ("HBM/후공정", "두산테스나", "131970"),
    ("HBM/후공정", "ISC", "095340"),
    ("HBM/후공정", "네패스", "033640"),
    ("HBM/후공정", "엑시콘", "190650"),
    ("HBM/후공정", "리노공업", "058470"),
    ("HBM/후공정", "HPSP", "403870"),
    ("HBM/후공정", "원익IPS", "240810"),
    ("HBM/후공정", "고영", "098460"),
    ("HBM/후공정", "에스앤에스텍", "101490"),
    ("HBM/후공정", "하나마이크론", "067310"),
    ("HBM/후공정", "파크시스템스", "140860"),
    ("HBM/후공정", "코세스", "089890"),
    ("HBM/후공정", "티에스이", "131290"),
    # ── 방산 ──
    ("방산", "LIG넥스원", "079550"),
    ("방산", "한화에어로스페이스", "012450"),
    ("방산", "풍산", "103140"),
    ("방산", "한화", "000880"),
    ("방산", "엘앤에프", "066970"),
    ("방산", "SNT다이내믹스", "100840"),
    ("방산", "화승엔터프라이즈", "241560"),
    ("방산", "빅텍", "065450"),
    ("방산", "에스원", "012750"),
    ("방산", "에이피", "278470"),
    ("방산", "우주일렉트로", "065370"),
    ("방산", "한국항공우주", "047810"),
    # ── 우주항공 ──
    ("우주항공", "한국항공우주", "047810"),
    ("우주항공", "우주일렉트로", "065370"),
    ("우주항공", "링크솔루션스", "294570"),
    ("우주항공", "티엘비", "356860"),
    ("우주항공", "인텔리안테크", "189300"),
    ("우주항공", "AP위성", "211270"),
    ("우주항공", "와이지엔테크", "122870"),
    ("우주항공", "코나아이", "052600"),
    # ── 조선 기자재 ──
    ("조선 기자재", "HD한국조선해양", "009540"),
    ("조선 기자재", "삼성중공업", "010140"),
    ("조선 기자재", "HJ중공업", "097230"),
    ("조선 기자재", "성광벤드", "014620"),
    ("조선 기자재", "일진하이솔루스", "271940"),
    ("조선 기자재", "대양전기공업", "108380"),
    ("조선 기자재", "HMM", "011200"),
    ("조선 기자재", "팬오션", "028670"),
    ("조선 기자재", "HD현대마린솔루션", "443060"),
    ("조선 기자재", "STX엔진", "077970"),
    ("조선 기자재", "성도이엔지", "015890"),
    ("조선 기자재", "삼영엠텍", "054540"),
    ("조선 기자재", "화신", "126700"),
    ("조선 기자재", "신성이엔지", "101930"),
    # ── LNG/보냉재 ──
    ("LNG/보냉재", "메타케어", "118000"),
    ("LNG/보냉재", "엘케이", "091970"),
    ("LNG/보냉재", "HD현대마린엔진", "071970"),
    ("LNG/보냉재", "일진하이솔루스", "271940"),
    ("LNG/보냉재", "성광벤드", "014620"),
    ("LNG/보냉재", "대양전기공업", "108380"),
    ("LNG/보냉재", "고려제강", "002240"),
    ("LNG/보냉재", "한온시스템", "018880"),
    ("LNG/보냉재", "세아제강", "306200"),
    ("LNG/보냉재", "포스코인터내셔널", "047050"),
    # ── 전력기기 ──
    ("전력기기", "LS ELECTRIC", "010120"),
    ("전력기기", "일진전기", "103590"),
    ("전력기기", "보성파워텍", "006910"),
    ("전력기기", "인텍", "129260"),
    ("전력기기", "제룡전기", "033100"),
    ("전력기기", "SK시그넷", "260870"),
    ("전력기기", "한전KPS", "051600"),
    ("전력기기", "광명전기", "017040"),
    ("전력기기", "효성티앤씨", "298020"),
    ("전력기기", "대한전선", "001440"),
    ("전력기기", "삼화콘덴서", "001820"),
    # ── 전선 ──
    ("전선", "대한전선", "001440"),
    ("전선", "가온전선", "000500"),
    ("전선", "광명전기", "017040"),
    ("전선", "LS", "006260"),
    ("전선", "일진전기", "103590"),
    ("전선", "대원전선", "006340"),
    ("전선", "서전", "189860"),
    ("전선", "일흥", "003720"),
    ("전선", "금호전기", "001210"),
    ("전선", "가온칩스", "399720"),
    # ── 원전 ──
    ("원전", "두산에너빌리티", "034020"),
    ("원전", "HD현대인프라코어", "042670"),
    ("원전", "한전산전", "130660"),
    ("원전", "우진", "105840"),
    ("원전", "태웅", "044490"),
    ("원전", "성광벤드", "014620"),
    ("원전", "한화솔루션", "009830"),
    ("원전", "일진파워", "103590"),
    ("원전", "한전기술", "052690"),
    ("원전", "티에이치엔진", "019180"),
    ("원전", "SK", "034730"),
    # ── AI 인프라 ──
    ("AI 인프라", "LG디스플레이", "034220"),
    ("AI 인프라", "네패스", "033640"),
    ("AI 인프라", "ISC", "095340"),
    ("AI 인프라", "DB하이텍", "000990"),
    ("AI 인프라", "리노공업", "058470"),
    ("AI 인프라", "한미반도체", "042700"),
    ("AI 인프라", "파크시스템스", "140860"),
    ("AI 인프라", "고영", "098460"),
    ("AI 인프라", "실리콘투", "257720"),
    # ── 데이터센터 ──
    ("데이터센터", "DB하이텍", "000990"),
    ("데이터센터", "리노공업", "058470"),
    ("데이터센터", "네패스", "033640"),
    ("데이터센터", "ISC", "095340"),
    ("데이터센터", "두산테스나", "131970"),
    ("데이터센터", "실리콘투", "257720"),
    ("데이터센터", "HPSP", "403870"),
    ("데이터센터", "원익IPS", "240810"),
    ("데이터센터", "코세스", "089890"),
    ("데이터센터", "티에스이", "131290"),
    ("데이터센터", "한미반도체", "042700"),
    ("데이터센터", "에이디테크", "200710"),
    ("데이터센터", "유니테스트", "088390"),
    ("데이터센터", "LG디스플레이", "034220"),
    # ── 로봇/자동화 ──
    ("로봇/자동화", "로보스타", "090360"),
    ("로봇/자동화", "레인보우로보틱스", "277810"),
    ("로봇/자동화", "로봇엔지니어링", "108490"),
    ("로봇/자동화", "휴림로봇", "090710"),
    ("로봇/자동화", "두산로보틱스", "454910"),
    ("로봇/자동화", "유진로봇", "056080"),
    ("로봇/자동화", "스맥", "099440"),
    ("로봇/자동화", "TPC", "048770"),
    ("로봇/자동화", "에스피지", "058610"),
    ("로봇/자동화", "하이젠", "160190"),
    ("로봇/자동화", "티로보틱스", "117730"),
    ("로봇/자동화", "에스비비테크", "389500"),
    ("로봇/자동화", "현대무벡스", "319400"),
    ("로봇/자동화", "삼현", "437730"),
)

# 티커 중복 제거 (섹터·종목 첫 항목만)
_seen_tickers: set[str] = set()
_DEDUPED_POOL: list[tuple[str, str, str]] = []
for sector, name, ticker in _CANDIDATE_POOL:
    code = ticker.zfill(6)
    if code in _seen_tickers:
        continue
    _seen_tickers.add(code)
    _DEDUPED_POOL.append((sector, name, code))

_WATCHLIST = watchlist_ticker_set()

# 스캔 순서 — 앞 섹터부터 candidate_limit 적용
SCAN_SECTOR_PRIORITY: tuple[str, ...] = (
    "반도체 장비",
    "HBM/후공정",
    "PCB/기판",
    "전력기기",
    "방산",
    "조선 기자재",
)


def sector_scan_priority(sector_name: str) -> int:
    try:
        return SCAN_SECTOR_PRIORITY.index(sector_name)
    except ValueError:
        return len(SCAN_SECTOR_PRIORITY)


def is_preferred_stock(name: str, ticker: str) -> bool:
    """
    우선주 후보 제외.
    - 알려진 우선주 티커
    - 종목명이 '우'로 끝남 (대우 등 보통주 예외)
    """
    code = str(ticker or "").strip().zfill(6)
    if code in KNOWN_PREFERRED_TICKERS:
        return True
    n = str(name or "").strip()
    if not n or n in _PREFERRED_NAME_FALSE_POSITIVES:
        return False
    if len(n) >= 4 and n.endswith("우"):
        return True
    return False


def candidate_sector_names() -> list[str]:
    order: list[str] = []
    for sector, _, _ in _DEDUPED_POOL:
        if sector not in order:
            order.append(sector)
    return order


def iter_candidate_entries(
    *,
    exclude_watchlist: bool = True,
    exclude_large_caps: bool = True,
    exclude_preferred: bool = True,
) -> Iterator[dict[str, Any]]:
    """Yield {sector_name, name, ticker} — watchlist·대형주·우선주 제외."""
    for entry in list_candidate_entries(
        exclude_watchlist=exclude_watchlist,
        exclude_large_caps=exclude_large_caps,
        exclude_preferred=exclude_preferred,
    ):
        yield entry


def list_candidate_entries(
    *,
    exclude_watchlist: bool = True,
    exclude_large_caps: bool = True,
    exclude_preferred: bool = True,
    scan_limit: int | None = None,
) -> list[dict[str, Any]]:
    """섹터 우선순위 정렬 후, scan_limit>0 이면 상위 N개만."""
    entries: list[dict[str, Any]] = []
    for sector, name, ticker in _DEDUPED_POOL:
        if exclude_watchlist and ticker in _WATCHLIST:
            continue
        if exclude_large_caps and ticker in EXCLUDED_LARGE_CAPS:
            continue
        if exclude_preferred and is_preferred_stock(name, ticker):
            continue
        entries.append(
            {
                "sector_name": sector,
                "name": name,
                "symbol": name,
                "ticker": ticker,
            }
        )
    entries.sort(
        key=lambda e: (sector_scan_priority(str(e["sector_name"])), str(e["name"]))
    )
    if scan_limit is not None and scan_limit > 0:
        return entries[:scan_limit]
    return entries


def candidate_universe_size(
    *,
    exclude_watchlist: bool = True,
    exclude_large_caps: bool = True,
    exclude_preferred: bool = True,
) -> int:
    return sum(
        1
        for _ in iter_candidate_entries(
            exclude_watchlist=exclude_watchlist,
            exclude_large_caps=exclude_large_caps,
            exclude_preferred=exclude_preferred,
        )
    )


def candidate_pool_stats(
    *,
    include_large_caps: bool = False,
) -> dict[str, int]:
    """풀·제외·스캔 대상 집계 (로그용)."""
    pool_total = len(_DEDUPED_POOL)
    excluded_watchlist = 0
    excluded_large_caps = 0
    excluded_preferred = 0
    for _sector, name, ticker in _DEDUPED_POOL:
        if ticker in _WATCHLIST:
            excluded_watchlist += 1
        if not include_large_caps and ticker in EXCLUDED_LARGE_CAPS:
            excluded_large_caps += 1
        if is_preferred_stock(name, ticker):
            excluded_preferred += 1
    pool_scan_target = candidate_universe_size(
        exclude_large_caps=not include_large_caps,
    )
    return {
        "pool_total": pool_total,
        "excluded_watchlist": excluded_watchlist,
        "excluded_large_caps": excluded_large_caps,
        "excluded_preferred": excluded_preferred,
        "pool_scan_target": pool_scan_target,
        # 하위 호환
        "pool_deduped": pool_total,
        "iterable": pool_scan_target,
    }
