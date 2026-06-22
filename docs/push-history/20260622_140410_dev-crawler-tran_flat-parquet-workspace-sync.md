# crawler-tran flat parquet 워크스페이스 반영

- Created at: 2026-06-22 14:04:10
- Branch: dev/crawler-tran
- Remote target: origin/dev/crawler-tran
- Source workspace: `C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test`
- Base repository: `https://github.com/K-Ternag/crawlService`
- Base branch: `main`

## Purpose

`crawler-tran-flat-test`에서 검증한 현재 크롤러 소스 상태를 `K-Ternag/crawlService`의 새 브랜치 `dev/crawler-tran`으로 게시한다.

핵심 목적은 개발팀 요청에 맞춘 `tran` parquet flat 저장 구조를 공유 가능한 브랜치에 올리는 것이다. 다만 GitHub `main`은 현재 로컬 테스트 워크스페이스보다 이전 상태이므로, 이번 브랜치에는 그동안 누적된 크롤러/오케스트레이션/중복 진단/rollup/API형 수집 코드도 함께 포함된다.

## Why This Change Was Needed

개발팀은 `filter` 산출물을 parquet으로 변환할 때 기존처럼 하위 폴더 구조를 유지하지 않고, 모든 parquet 파일을 `tran` 바로 아래 같은 depth에 생성하기를 요청했다.

요구 사항은 다음과 같았다.

- `tran` 아래 하위 폴더를 만들지 않는다.
- 파일명은 원본 파일명 뒤에 `.parquet`을 붙이는 방식이 아니라 `download_YYYYMMDD_HHMISSffffff.parquet`, `text_YYYYMMDD_HHMISSffffff.parquet`, `metadata_YYYYMMDD_HHMISSffffff.parquet` 형식을 따른다.
- timestamp는 `pub_date`가 아니라 원본 파일의 수집 시각 기준이어야 한다.
- `workflow_records.json`은 `metadata_*.parquet`로 변환한다.
- `metadata_*.parquet`에는 원본 `workflow_records.json` bytes와 원본 파일-변환 parquet 매칭 manifest를 담는다.
- `latest.json`과 `filter/rollup/**`은 변환 대상에서 제외한다.
- `source_sha256`은 쓰지 않고 `source_file_name`과 `source_relative_path`로 매핑한다.

## What Changed

### Source and Workflow

- `crawler_app/workflow.py`
  - `filter` 산출물 parquet export를 flat 구조로 변경했다.
  - `download`, `text`, `metadata`, 기타 `file` kind를 경로 기준으로 판정한다.
  - 원본 파일의 `mtime_ns`를 KST `collected_at`으로 변환해 파일명 timestamp와 row metadata에 사용한다.
  - 같은 `kind + timestamp` 파일명이 겹치면 `_001`, `_002` suffix로 충돌을 방어한다.
  - 각 parquet row에 `source_relative_path`, `source_file_name`, `tran_kind`, `collected_at`, `content_bytes`, `exported_at`을 저장한다.
  - `metadata_*.parquet`에는 추가로 `tran_manifest_json`을 저장한다.
  - `latest.json`과 `filter/rollup/**`은 변환 대상에서 제외한다.

### Tests and Documentation

- `tests/test_tran_parquet_export.py`
  - flat depth, kind timestamp naming, collision suffix, latest/rollup 제외, metadata manifest, schema를 검증하는 테스트를 추가했다.
- `docs/tran-flat-parquet-change-rationale.md`
  - 변경 이유와 설계 판단, tradeoff, 검증 기준을 문서화했다.

### Included Current Workspace State

GitHub `main` 대비 현재 워크스페이스에는 다음 누적 기능도 포함되어 있다.

- 오케스트레이션 페이지와 Windows Task Scheduler 연동
- scheduled runner와 scheduler runtime log
- workflow records rollup 및 `/api/workflow-records`
- Naver/Daum/Google API/RSS parser 계층
- latest 기반 중복 진단과 API recent URL index
- DART/ZIP 다운로드 후처리
- category/crawling_type 기본정보 기록
- 운영 config 추가/정리
- UI progress, orchestration 상태 표시, scheduler 관리 화면
- 관련 테스트와 운영 문서

## Design Judgment

`tran` 파일명을 원본 파일명 기반으로 유지하면 파일명 길이와 폴더 깊이가 커지고, 개발팀이 원하는 flat ingestion 구조와 맞지 않는다. 대신 `metadata_*.parquet`의 `tran_manifest_json`과 각 parquet row의 `source_relative_path`, `source_file_name`으로 원본과 변환 파일을 연결하도록 했다.

이 설계는 parquet 파일명은 짧고 정규화하면서도, 원본 추적성을 metadata로 보존한다.

## Alternatives Considered Or Deferred

- 원본 파일명을 parquet 파일명에 그대로 남기는 방식은 flat 구조의 이점이 작고 파일명이 과도하게 길어져 제외했다.
- `source_sha256`을 추가하는 방식은 사용자가 원하지 않아 제외했다.
- 다운로드 단계에 sleep을 넣는 방식은 현재 수집 loop가 순차 실행이고 충돌은 변환 단계에서 방어 가능하므로 보류했다.
- rollup archive parquet 변환은 이번 정책에서 제외했다.

## Validation

다음 검증을 수행했다.

```powershell
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m compileall crawler_app crawlers main.py
C:\AI_JOB\firstproject\crawler_project\crawler-tran-flat-test\.venv\Scripts\python.exe -m unittest tests.test_tran_parquet_export -v
node --check static\app.js
```

검증 결과:

- Python compile 통과
- `tests.test_tran_parquet_export` 통과
- `static/app.js` syntax check 통과

실제 output 검증도 수행했다.

- 현재 `metadata_*.parquet` 6개 기준 manifest entry 546개 확인
- 일반 파일 entry 540개 모두 원본 `filter` 파일과 변환 `tran` parquet 존재
- manifest 값과 각 parquet row의 `source_relative_path`, `source_file_name`, `tran_kind`, `collected_at` 일치
- `_001.parquet` 충돌 suffix 발생 0건
- latest/rollup 변환 흔적 없음

## Secret And Artifact Checks

다음은 제외했다.

- `.venv`
- `outputs`
- `runtime`
- `logs`
- `orchestration_state`
- `imsi`
- `attach`
- Python cache files
- `.env`

secret scan에서는 실제 credential 값은 발견되지 않았다. 발견된 항목은 `.env.example` placeholder, README의 `<Gmail app password>` 예시, 환경변수명 및 보안 가이드 문구였다.

## Remaining Risks

- GitHub `main`이 현재 로컬 워크스페이스보다 많이 뒤처져 있어 이번 브랜치 diff가 크다.
- 일부 output 폴더는 현재 runtime 상태에서 `metadata_*.parquet`이 없는 tran 파일만 남아 있었다. 소스 로직상 새 export 시 metadata를 생성하지만, 기존 runtime 산출물은 과거 실행 상태가 섞일 수 있다.
- 전체 회귀 테스트를 모두 실행하지 않고, 이번 push 전에는 compile, tran parquet 단위 테스트, JS syntax check 중심으로 검증했다.
- Windows Task Scheduler 실제 등록/삭제 검증은 이번 push 직전에는 반복하지 않았다. 이전 로컬 검증에서 wrapper가 `.venv`를 잡고 exit code 0으로 실행되는 것은 확인했다.

## Cumulative Prompt / Request Flow

사용자는 개발팀 요청에 따라 `tran` parquet 저장 구조를 flat하게 바꾸고, `metadata_*.parquet`으로 원본 파일과 변환 parquet을 매칭할 수 있는 구조를 요구했다. 원본 프로젝트를 바로 수정하지 않고 `crawler-tran-flat-test` 복사 워크스페이스에서 먼저 구현/검증했다.

이후 사용자는 실제 `outputs` 기준으로 metadata parquet 내부 데이터와 원본/변환 파일 매칭 여부를 확인해 달라고 요청했다. 검증 결과 metadata가 있는 output에서는 manifest 기반 매칭이 정상임을 확인했고, 시간 충돌 suffix가 없음을 확인했다.

마지막으로 사용자는 현재 워크스페이스 소스 상태를 `K-Ternag/crawlService`에 새 브랜치 `dev/crawler-tran`으로 push하도록 요청했다.

## Pre-Commit Checklist

- [x] Only task-related files are staged.
- [x] No unrelated runtime artifacts are staged.
- [x] No `.env`, API key, token, password, app password, cookie, or sensitive log is staged.
- [x] Push record is included in the same commit.
- [x] Validation results are recorded honestly.
- [x] Remaining risks are recorded honestly.
