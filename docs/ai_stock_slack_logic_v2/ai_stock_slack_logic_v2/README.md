# AI 관심종목 스캔 + 슬랙 알림 시스템 설계

이 문서는 국장 관심종목 기반 자동 스캔/슬랙 알림 시스템을 구현하기 위한 작업 문서다.

핵심 목적은 전체 시장 추천이 아니라, 미리 정한 관심 섹터와 관심종목 안에서만 장중 흐름을 감시하고, 1주 테스트 진입을 검토할 만한 종목만 슬랙으로 알려주는 것이다.

## 문서 구성

- `01_watchlist.md` : 관심 섹터/종목 기준
- `02_message_goal.md` : 메시지 발송 목표와 방향
- `03_scan_logic.md` : 데이터 수집 및 선별 로직
- `04_agents.md` : AI 에이전트별 임무
- `05_schedule.md` : 장중 실행 시간대
- `06_slack_message.md` : 슬랙 메시지 포맷
- `07_system_changes.md` : 시스템 수정 요구사항
- `08_cursor_prompt.md` : Cursor 전체 구현 프롬프트
- `09_task_queue.md` : 순차 작업 체크리스트
- `10_progress.md` : Cursor 진행 기록 파일

## 작업 방식

한 번에 모든 문서를 처리하지 말고, `09_task_queue.md` 기준으로 1개 문서씩 순차 반영한다.

Cursor에게는 다음처럼 지시한다.

```text
09_task_queue.md와 10_progress.md를 확인해서 아직 처리하지 않은 첫 번째 md 파일 1개만 반영해줘.
작업 완료 후 09_task_queue.md에 체크하고, 10_progress.md에 수정 내용과 다음 작업을 기록한 뒤 멈춰.
```
