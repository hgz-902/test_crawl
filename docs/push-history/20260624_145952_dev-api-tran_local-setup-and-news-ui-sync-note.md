# dev/API+Tran 로컬 설치 및 뉴스 UI 데이터 생성 안내

## 목적

`dev/API+Tran` 브랜치를 다른 로컬 또는 Windows 서버에서 받은 뒤, Parquet 전환 UI와 SQLite 기반 뉴스 검토 API를 정상적으로 사용하기 위해 필요한 설치 및 초기 데이터 생성 절차를 문서화한다.

이번 기록은 코드 변경이 아니라 운영/전달용 push-history 보강이다. 개발 팀이 새 환경에서 코드를 받은 뒤 `/api/news`, `/api/news/grouped`, `/api/filter-options`, `/api/stats`가 왜 비어 보일 수 있는지와 어떤 명령을 실행해야 하는지 확인할 수 있게 하는 것이 목적이다.

## 핵심 판단

- 코드만 clone/pull한 직후에는 SQLite 뉴스 UI DB가 비어 있을 수 있다.
- 뉴스 UI API는 `outputs/**/filter/**/workflow_records.json`을 SQLite로 적재한 뒤 동작한다.
- `filter-options` 데이터는 별도 수동 파일에서 만드는 것이 아니라 SQLite sync 과정에서 자동 재생성된다.
- 유사 기사 그룹핑도 API 호출 시 실시간 계산하지 않고 SQLite sync 중 사전 계산한다.
- Parquet 전환 UI는 `outputs/*/tran/*.parquet` 파일을 읽으므로, parquet 파일이 존재해야 목록에 표시된다.

## 필수 설치

새 로컬에서 저장소를 받은 뒤 아래 명령으로 Python 가상환경과 의존성을 준비한다.

```powershell
cd C:\AI_JOB\firstproject\crawler_project\crawlService

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

`requirements.txt`의 주요 런타임 의존성은 다음과 같다.

- `pyarrow`: Parquet 전환 메뉴에서 parquet 읽기와 원본 다운로드 변환에 사용
- `sentence-transformers`: 제목 기반 유사 기사 그룹핑 모델에 사용
- `playwright`: 기존 크롤러 실행에 사용
- `fastapi`, `uvicorn`, `jinja2`: 웹 UI/API 서버 실행에 사용

## 유사 기사 그룹핑 모델

기본 모델은 다음 값이다.

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

처음 실행하는 환경에서는 Hugging Face 모델 다운로드가 발생할 수 있으므로 인터넷 연결이 필요할 수 있다. 모델 기반 그룹핑이 반드시 사용되는지 확인하고 싶다면 아래 환경변수를 설정한다.

```powershell
$env:NEWS_GROUPING_REQUIRE_MODEL="true"
```

모델 로드가 실패하면 기본 구현은 lexical fallback을 사용할 수 있다. 운영 검수에서는 모델 다운로드 성공 여부와 `runtime/news_ui/last_sync_summary.json`의 그룹핑 소요 시간을 함께 확인한다.

## SQLite 뉴스 UI DB 생성

뉴스 목록, 그룹 보기, 필터 옵션, 통계 API는 기본적으로 아래 SQLite DB를 사용한다.

```text
runtime/news_ui/news_ui.sqlite3
```

이미 수집된 `outputs`를 새 환경에 복사했거나, clone 직후 기존 output을 기준으로 UI API를 확인하려면 아래 명령을 한 번 실행한다.

```powershell
.\.venv\Scripts\python.exe -m crawler_app.news_ingestion --project-root . --rebuild
```

이 명령은 다음 작업을 수행한다.

- `outputs/**/filter/**/workflow_records.json` 읽기
- `crawl_articles`에 기사 upsert
- `crawl_filter_options` 재생성
- 제목 기반 감성분석 저장
- 같은 날짜 기사 기준 유사 기사 그룹핑 생성
- `runtime/news_ui/last_sync_summary.json`에 sync/감성/그룹핑 소요시간 기록

수동 실행 또는 오케스트레이션 실행으로 새 크롤링 결과가 생성되는 경우에는 실행 종료 후 `_sync_news_ui_from_result()` 또는 `_sync_news_ui_from_job_output()` 경로를 통해 SQLite sync가 자동 수행된다.

## 서버 실행

```powershell
.\.venv\Scripts\python.exe -m uvicorn crawler_app.web:app --host 127.0.0.1 --port 3010
```

확인용 API 호출 예시는 다음과 같다.

```powershell
Invoke-RestMethod "http://127.0.0.1:3010/api/filter-options"
Invoke-RestMethod "http://127.0.0.1:3010/api/news?user_id=unknown&page=1&page_size=20"
Invoke-RestMethod "http://127.0.0.1:3010/api/news/grouped?user_id=unknown&page=1&page_size=20"
Invoke-RestMethod "http://127.0.0.1:3010/api/stats?user_id=unknown"
```

## 검증 포인트

- `/api/filter-options`에 `sources`, `search_terms`가 채워지는지 확인한다.
- `/api/news/grouped`에서 `totalCount`와 `totalArticles`가 반환되는지 확인한다.
- `runtime/news_ui/last_sync_summary.json`에서 `articles_upserted`, `sentiments_written`, `grouping_duration_seconds`를 확인한다.
- Parquet 전환 메뉴는 `/parquet-converter`에서 확인한다.
- Parquet 목록은 `outputs/*/tran/*.parquet`가 있을 때만 표시된다.

## 남은 리스크

- 새 로컬에서 모델 다운로드가 막혀 있으면 유사 기사 그룹핑이 lexical fallback으로 동작할 수 있다.
- `outputs`가 없거나 `workflow_records.json`이 없으면 SQLite DB와 filter-options는 비어 있는 것이 정상이다.
- 기존 서버 포트가 이미 사용 중이면 `--port` 값을 바꿔 실행해야 한다.
