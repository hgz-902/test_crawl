# 뉴스 검토 UI API 검증 증거

## Acceptance Criteria

- 크롤링 서버에 뉴스 검토 UI가 호출하는 API를 추가한다.
- Databricks 의존 없이 SQLite를 사용한다.
- `workflow_records.json` 적재 시 기사, 필터 옵션, 배치 감성분석, 같은 날짜 유사 기사 그룹핑을 사전 계산한다.
- API 호출 시 그룹핑 임베딩을 계산하지 않는다.
- 기존 parquet 전환 기능이 깨지지 않아야 한다.
- 직접 LLM 분석 API는 크롤링 서버에 포함하지 않고, 별도 분석 서비스가 저장 API를 호출할 수 있는 구조를 유지한다.

## Critical Review

Findings:
- FIXED: LLM 분석 저장이 기존 배치 감성분석 row를 덮을 때 `confidence`가 이전 배치 값으로 남을 수 있었다. `save_article_analysis()`에서 `confidence=NULL`, `analyzed_at` 갱신을 명시하도록 수정하고 회귀 테스트를 추가했다.

Open questions:
- 실제 프론트엔드의 분석 결과 저장/조회 화면 요청/응답 필드가 현재 공유 코드와 완전히 같은지 추가 확인이 필요하다.
- 운영 내부 모델이 분석 결과를 어떤 방식으로 저장 API에 전달할지 확인이 필요하다.

## QA Test Result

- PASS: `.venv\Scripts\python.exe -m compileall crawler_app`
- PASS: `.venv\Scripts\python.exe -m unittest tests.test_news_ui_api -v`
- PASS: `.venv\Scripts\python.exe -m unittest tests.test_web.ParquetConverterRouteTests -v`
- PASS: `.venv\Scripts\python.exe -c "import sentence_transformers; ..."`
- PASS: `.venv\Scripts\python.exe -c "from crawler_app.news_sentiment import analyze_sentiment; ..."`

## Red-Team Review

- SQL injection: 로컬 SQLite query는 parameter binding 중심으로 작성했다. 개발팀 원문 `main.py`의 f-string SQL은 그대로 이식하지 않았다.
- Secrets: 분석 결과 저장/조회 API는 API key를 받거나 저장하지 않는다.
- External side effects: 크롤링 서버는 직접 LLM 호출 엔드포인트를 제공하지 않는다.
- Storage: SQLite 기본 경로는 `runtime/news_ui/news_ui.sqlite3`로 제한했다.

## Decision Ruling

Conditional pass.

조건:
- 실제 프론트엔드 분석 UI와 연결하기 전, `/analysis/save`, `/analysis`의 요청/응답 필드 호환성을 한 번 더 확인해야 한다.
- 운영 전에는 내부 모델이 생성한 분석 결과 저장 주체와 호출 타이밍을 확정해야 한다.
