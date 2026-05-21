"""MVP 4 — 관심 섹터 신규 후보군 (watchlist 제외용 임시 유니버스)."""

from __future__ import annotations

from typing import Any, Iterator

from data.kr_watchlist import watchlist_ticker_set

# (sector_name, name, ticker) — kr_watchlist 25종목과 겹치지 않도록 별도 풀
_CANDIDATE_POOL: tuple[tuple[str, str, str], ...] = (
    # 반도체 소재
    ("반도체 소재", "솔브레인", "357780"),
    ("반도체 소재", "후성", "093370"),
    ("반도체 소재", "SK아이이테크놀로지", "361610"),
    ("반도체 소재", "덕산네오룩스", "213420"),
    ("반도체 소재", "이엔에프테크놀로지", "102710"),
    # 반도체 부품
    ("반도체 부품", "이수페타시스", "007660"),
    ("반도체 부품", "대덕", "008060"),
    ("반도체 부품", "심텍홀딩스", "036710"),
    ("반도체 부품", "이수화학", "005950"),
    ("반도체 부품", "LG이노텍", "011070"),
    ("반도체 부품", "삼성전기", "009150"),
    # 반도체 장비
    ("반도체 장비", "HPSP", "403870"),
    ("반도체 장비", "원익IPS", "240810"),
    ("반도체 장비", "리노공업", "058470"),
    ("반도체 장비", "GST", "083450"),
    ("반도체 장비", "케이씨텍", "281820"),
    ("반도체 장비", "레이크머티리얼즈", "281740"),
    # 방산·우주
    ("방산·우주", "LIG넥스원", "079550"),
    ("방산·우주", "한국항공우주", "047810"),
    ("방산·우주", "한화에어로스페이스", "012450"),
    ("방산·우주", "풍산", "103140"),
    ("방산·우주", "우주일렉트로", "065370"),
    # 조선 기자재
    ("조선 기자재", "HD한국조선해양", "009540"),
    ("조선 기자재", "삼성중공업", "010140"),
    ("조선 기자재", "HJ중공업", "097230"),
    ("조선 기자재", "성광벤드", "014620"),
    ("조선 기자재", "일진하이솔루스", "271940"),
    ("조선 기자재", "대양전기공업", "108380"),
    # 전력/에너지
    ("전력/에너지", "HD현대일렉트릭", "267260"),
    ("전력/에너지", "LS ELECTRIC", "010120"),
    ("전력/에너지", "효성중공업", "298040"),
    ("전력/에너지", "일진전기", "103590"),
    ("전력/에너지", "대한전선", "001440"),
    ("전력/에너지", "보성파워텍", "006910"),
    # AI 인프라
    ("AI 인프라", "LG디스플레이", "034220"),
    ("AI 인프라", "SK하이닉스", "000660"),
    ("AI 인프라", "삼성전자", "005930"),
    ("AI 인프라", "네패스", "033640"),
    ("AI 인프라", "ISC", "095340"),
    ("AI 인프라", "리노공업", "058470"),
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

# watchlist와 겹치는 티커는 유니버스에서 제외
_WATCHLIST = watchlist_ticker_set()


def candidate_sector_names() -> list[str]:
    order: list[str] = []
    for sector, _, _ in _DEDUPED_POOL:
        if sector not in order:
            order.append(sector)
    return order


def iter_candidate_entries(*, exclude_watchlist: bool = True) -> Iterator[dict[str, Any]]:
    """Yield {sector_name, name, ticker} — 기본적으로 watchlist 티커 제외."""
    for sector, name, ticker in _DEDUPED_POOL:
        if exclude_watchlist and ticker in _WATCHLIST:
            continue
        yield {
            "sector_name": sector,
            "name": name,
            "ticker": ticker,
            "symbol": name,
        }


def candidate_universe_size(*, exclude_watchlist: bool = True) -> int:
    return sum(1 for _ in iter_candidate_entries(exclude_watchlist=exclude_watchlist))
