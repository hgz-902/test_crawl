# 설정 목록 검색어/필터 복원

- 일시: 2026-06-22 15:14 KST
- 브랜치: `dev/crawler-tran`
- 대상: `configs/*.json`

## 목적

설정 목록에서 사라진 검색어 목록과 필터 목록을 복원한다.

## 변경 내용

- `origin/dev/crawler-current` 기준으로 `search_terms`, `filter_terms`를 현재 워크스페이스 설정에 반영했다.
- `search_terms`가 비어 있으면서 `{search_term}`이 페이지 번호 파라미터로 쓰이는 설정에는 1~3페이지 수집용 값을 추가했다.
  - `마켓인사이트.json`: `["1", "2", "3"]`
  - `시그널.json`: `["1", "2", "3"]`
  - `인베스트조선.json`: `["1", "2", "3"]`
  - `중국 세관.json`: `["1", "2", "3"]`
- 검색어 파라미터형인데 비어 있는 설정은 발견되지 않았다.

## 검증

- `configs/*.json` 74개 전체 JSON 파싱 확인.
- `crawler_app.config_store.list_configs()`로 대표 설정의 `search_terms`, `filter_terms` 로딩 확인.

## 제외

- 코드, outputs, runtime, logs, parquet 산출물은 포함하지 않았다.
