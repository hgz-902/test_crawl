# 뉴스 검토 UI API 로컬 백엔드 변경 근거

## Change Rationale

- Changed area: `crawler_app/news_*.py`, `crawler_app/web.py`, `requirements.txt`
- Existing behavior: 크롤러 웹 서버는 설정 관리, 수동 실행, 오케스트레이션, workflow records 조회, parquet 전환 기능만 제공했다. 개발팀이 공유한 뉴스 검토 UI API는 Databricks SQL/Delta/Vector Search 기반이라 로컬 Windows 크롤링 서버에서 바로 사용할 수 없었다.
- Requested behavior: 크롤링 서버에 UI 호출 API를 붙이고, 로컬 SQLite에서 기사 목록, 그룹 보기, 통계, 읽음/즐겨찾기, 감성분석, LLM 분석 저장/조회 흐름을 제공한다.
- Why config/UI/templates/scripts were not enough: API 응답은 `crawl_articles`, `article_clusters`, `article_sentiment`, `user_article_state` 같은 영속 상태와 사전 그룹핑 결과에 의존하므로 설정 변경만으로는 구현할 수 없다.
- Source change made:
  - `news_sqlite_store.py`: Databricks Delta schema를 SQLite schema와 query/upsert 함수로 이식.
  - `news_ingestion.py`: `outputs/**/filter/workflow_records*.json`을 SQLite에 적재하고 필터 옵션, 감성분석, 같은 날짜 그룹핑을 갱신.
  - `news_grouping.py`: Databricks Vector Search 대신 로컬 sentence-transformers 또는 lexical fallback 기반 유사 기사 그룹핑.
  - `news_sentiment.py`: 개발팀 노트북의 제목 키워드 기반 배치 감성분석을 로컬 모듈화.
  - `news_ui_api.py`: `/api/news`, `/api/news/grouped`, `/api/filter-options`, `/api/stats`, read/favorite, LLM analyze/save/get API 제공.
  - `web.py`: API router 연결, startup DB 초기화, 수동 크롤링 완료 후 output_dir 단위 DB 동기화.
- Tradeoff accepted: v1은 SQLite를 사용한다. 동시 쓰기와 대규모 분석이 커지면 PostgreSQL 또는 별도 배치 프로세스로 분리할 수 있다.
- Alternatives rejected:
  - Databricks SQL 직접 호출 유지: 로컬/Windows 서버 성능 문제와 운영 의존성 때문에 제외.
  - API 호출 시 유사도 실시간 계산: UI 응답 지연이 커져 개발팀 요구와 맞지 않아 제외.
  - 개발팀 원문 `main.py` 직접 병합: 오타, SQL injection 위험, Databricks 의존성 때문에 제외.
- Validation evidence:
  - `.venv\Scripts\python.exe -m compileall crawler_app`
  - `.venv\Scripts\python.exe -m unittest tests.test_news_ui_api -v`
  - `.venv\Scripts\python.exe -m unittest tests.test_web.ParquetConverterRouteTests -v`
- Remaining risk:
  - 실제 프론트엔드 분석 화면의 요청/응답 세부 필드가 추가로 다를 수 있다.
  - LLM API는 `OPENAI_API_KEY` 또는 `NEWS_LLM_API_KEY`가 없으면 503을 반환한다.
  - sentence-transformers 기본 모델은 최초 실행 시 모델 다운로드 시간이 발생할 수 있다. 필요 시 `NEWS_GROUPING_PROVIDER=lexical`로 모델 없이 실행할 수 있다.
