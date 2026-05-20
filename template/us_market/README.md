# us_market 템플릿

미국 시장 투자 인사이트 HTML 템플릿. `styles.css`는 kr_market과 **동일 베이스를 한 파일에 포함**(로컬 서버가 `us_market` 폴더만 서빙할 때 `@import ../kr`는 404로 스타일이 깨짐).

- Figma: [us_market node 110:3088](https://www.figma.com/design/CxxvVJfcOcZX6gEHjEp8Vb/?node-id=110-3088)
- 참고 스크린: `template/us_market.jpg`

## 로컬 미리보기

```bash
cd template/us_market
python -m http.server 8080 --bind 0.0.0.0
```

브라우저에서 `http://127.0.0.1:8080/index.html`

## Jinja 렌더

```bash
cd template/us_market
python render.py
# → preview.html
```

`sample_data.json`의 `m7_tabs` / `m7_stocks`로 탭·패널을 채웁니다.

## kr_market과 차이

| 항목 | kr_market | us_market |
|------|-----------|-----------|
| 메타 | 한국시장 | 미국시장 |
| 지표 | 코스피, 코스닥, 환율 | S&P500, Nasdaq, Gold, Silver |
| M7 섹션 | 없음 | 가로 탭 + 패널 전환 |
| 종목 KV | 외국인 순매수 등 | PER, 시가총액 등 (5행) |

## M7 탭 스타일 (Figma)

- 활성: `#31537e` 배경, 흰 글자, 높이 30px, pill radius
- 비활성: `#e9ecef` 배경, `#9aa3ae` 글자
- 탭 간격 8px, 가로 스크롤
