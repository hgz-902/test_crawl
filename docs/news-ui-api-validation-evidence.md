# 뉴스 검토 UI API 검증 증거

## Acceptance Criteria

- 크롤링 서버에 뉴스 검토 UI가 호출하는 API를 추가한다.
- Databricks 의존 없이 SQLite를 사용한다.
- `workflow_records.json` 적재 시 기사, 필터 옵션, 배치 감성분석, 같은 날짜 유사 기사 그룹핑을 사전 계산한다.
- API 호출 시 그룹핑 임베딩을 계산하지 않는다.
- 기존 parquet 전환 기능이 깨지지 않아야 한다.
- LLM 분석 API는 키/패키지 누락 시 서버 전체를 깨뜨리지 않고 해당 API에서 명확히 실패해야 한다.

## Critical Review

Findings:
- FIXED: LLM 분석 저장이 기존 배치 감성분석 row를 덮을 때 `confidence`가 이전 배치 값으로 남을 수 있었다. `save_article_analysis()`에서 `confidence=NULL`, `analyzed_at` 갱신을 명시하도록 수정하고 회귀 테스트를 추가했다.

Open questions:
- 실제 프론트엔드의 LLM 분석 화면 요청/응답 필드가 현재 공유 코드와 완전히 같은지 추가 확인이 필요하다.
- 운영 LLM endpoint가 OpenAI 호환인지, 별도 사내 gateway인지 확인이 필요하다.

## QA Test Result

- PASS: `.venv\Scripts\python.exe -m compileall crawler_app`
- PASS: `.venv\Scripts\python.exe -m unittest tests.test_news_ui_api -v`
- PASS: `.venv\Scripts\python.exe -m unittest tests.test_web.ParquetConverterRouteTests -v`
- PASS: `.venv\Scripts\python.exe -c "import openai, sentence_transformers; ..."`
- PASS: `.venv\Scripts\python.exe -c "from crawler_app.news_sentiment import analyze_sentiment; ..."`

## Red-Team Review

- SQL injection: 로컬 SQLite query는 parameter binding 중심으로 작성했다. 개발팀 원문 `main.py`의 f-string SQL은 그대로 이식하지 않았다.
- Secrets: LLM API key는 코드/DB에 저장하지 않고 `OPENAI_API_KEY` 또는 `NEWS_LLM_API_KEY` 환경변수에서만 읽는다.
- External side effects: `/api/news/{article_id}/analyze`만 외부 LLM 호출 가능성이 있다. 키가 없으면 503으로 실패한다.
- Storage: SQLite 기본 경로는 `runtime/news_ui/news_ui.sqlite3`로 제한했다.

## Decision Ruling

Conditional pass.

조건:
- 실제 프론트엔드 분석 UI와 연결하기 전, `/api/news/{article_id}/analyze`, `/analysis/save`, `/analysis`의 요청/응답 필드 호환성을 한 번 더 확인해야 한다.
- 운영 전에는 LLM endpoint/key 정책과 모델명을 확정해야 한다.
