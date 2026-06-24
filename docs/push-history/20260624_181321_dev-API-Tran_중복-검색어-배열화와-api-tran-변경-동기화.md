# 중복 검색어 배열화와 API/Tran 변경 동기화

- 일시: 2026-06-24 18:13 KST
- 대상 저장소: `K-Ternag/crawlService`
- 대상 브랜치: `dev/API+Tran`
- 작업 워크스페이스: `C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test`
- push용 repo: `C:\AI_JOB\firstproject\crawler_project\crawler-api-tran-push`

## 목적

개발팀 요청에 따라 `workflow_records.json`의 `search_term`, `filter_term`을 항상 배열 형태로 저장하고, 중복 진단 과정에서 같은 기사로 판정된 record의 검색어/필터어를 대표 record에 병합하는 변경을 `dev/API+Tran` 브랜치에 반영한다.

동시에 최근 `crawler-tran-flat-test`에 누적된 SQLite 뉴스 UI API, Parquet flat 변환 및 전환 UI, 오케스트레이션 실행 보완, 중복 key 진단 보완 내용을 K-Ternag 원격 브랜치와 동기화한다.

## 주요 변경 파일과 역할

- `crawler_app/workflow.py`
  - `workflow_records.json` snapshot 저장 시 `search_term`, `filter_term`을 배열로 정규화한다.
  - 기존 record 또는 같은 실행 내 중복 record가 발견되면 대표 record의 term 배열에 새 값을 병합한다.
  - `latest.json`은 내부 중복 경계 파일로 유지하되 배열 record를 받아도 기존 중복 판단이 깨지지 않도록 호환 처리한다.

- `crawler_app/duplicate_keys.py`
  - parser/API record의 중복 key 생성 규칙을 공통화하고, Google RSS 등에서 동일 기사 판단이 가능하도록 보조 key 생성을 보강한다.

- `crawler_app/news_ingestion.py`, `crawler_app/news_sqlite_store.py`
  - 배열형 `search_term`을 SQLite 적재 시 문자열로 안전하게 변환한다.
  - 뉴스 UI API가 기존 TEXT 스키마를 유지하면서도 배열형 workflow record를 읽을 수 있게 한다.

- `crawler_app/orchestration.py`, `scripts/Run-OrchestrationJob.ps1`
  - 오케스트레이션 수동/스케줄 실행 시 환경과 실행 경로를 안정화한다.

- `crawler_app/workflow_records_api.py`
  - 배열형 term을 화면/검색/정렬에서 사람이 읽을 수 있는 문자열로 처리한다.

- `requirements.txt`
  - 뉴스 UI API 및 parquet/SQLite 실험에 필요한 런타임 의존성을 정리한다.

- `tests/test_workflow.py`, `tests/test_news_ui_api.py`, `tests/test_workflow_records_api.py`
  - 중복 record 병합 시 term 배열이 유지/확장되는지 검증한다.
  - 뉴스 UI API와 workflow records API가 배열형 term을 처리하는지 검증한다.

## 설계 판단

- 개발팀 요구 대상은 `workflow_records.json`이므로 public output record는 배열형으로 통일했다.
- `latest.json`은 사용자 노출 산출물이 아니라 내부 중복 경계 파일이므로 기존 문자열 기반 동작을 유지했다.
- 중복 병합 시 제목, 본문, URL은 대표 record를 유지하고, 병합 대상은 `search_term`, `filter_term`에 한정했다.
- `filter_term` 다중 배열은 오류가 아니라 한 기사에 여러 필터어가 매칭되었다는 분류 정보로 해석한다.
- 페이지 파라미터형 `search_term`은 구조적으로 배열화될 수 있으나, 현재 검수 outputs에서는 숫자형 page parameter 병합 사례가 확인되지 않았다.

## 검증

다음 명령을 `C:\AI_JOB\firstproject\crawler_project\crawler-api-tran-push`에서 실행했다.

```powershell
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m compileall crawler_app
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m unittest tests.test_workflow tests.test_news_ui_api tests.test_workflow_records_api -v
```

결과:

- `compileall crawler_app`: 성공
- `unittest`: 91개 테스트 성공

## 비밀값 점검

- `.env`, API key, token, cookie, 비밀번호 파일은 staging 대상에 포함하지 않는다.
- push 대상은 소스, 테스트, requirements, PowerShell 실행 스크립트, push-history 문서로 제한한다.

## 남은 리스크

- 실제 운영에서 페이지 파라미터형 `search_term`이 여러 페이지에 걸쳐 병합되면 `search_term: ["1", "2"]`처럼 보일 수 있다. 이는 검색어 중복이 아니라 페이지 경계 중복으로 해석해야 한다.
- 장기적으로는 config에 `search_term` 의미가 `keyword`인지 `page_param`인지 구분하는 메타데이터를 추가하는 것이 더 명확하다.
- Parquet 전환 UI와 뉴스 UI API는 로컬 SQLite/파일 기반 구조이므로 운영 배포 시 경로, 권한, DB 백업 정책을 별도로 확인해야 한다.
