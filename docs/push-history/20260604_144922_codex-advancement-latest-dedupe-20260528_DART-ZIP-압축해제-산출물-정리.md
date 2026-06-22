# DART ZIP 압축해제 산출물 정리

- 일시: 2026-06-04 14:49:22 KST
- 저장소: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- 브랜치: `codex/advancement-latest-dedupe-20260528`
- push 대상: `origin codex/advancement-latest-dedupe-20260528`
- 커밋 메시지: `DART ZIP 압축해제 산출물 정리`

## 요청 / 작업 단위

전문가 지시 형태로 정리한 이번 작업 프롬프트:

> DART와 같이 다운로드 결과가 ZIP 압축본으로 내려오는 크롤러에서, ZIP 파일 자체를 최종 수집 산출물로 남기지 말고 내부 파일만 수집 산출물로 저장하라. 압축 해제 시 ZIP 전용 하위 폴더를 만들지 말고, 기존 다운로드 산출물과 동일하게 `downloads/YYYYMMDD` 바로 아래에 저장하라. 내부 파일명 앞에는 ZIP이나 임시 경로명이 아니라 수집 record key를 붙여, 예를 들어 `DART-3CWG5VZPC2FKO_원본문서.html`처럼 사이트 prefix가 포함된 동일한 record key 양식을 유지하라. ZIP 내부 경로는 평탄화하고, 동일 파일명이 있으면 suffix로 충돌을 피하며, path traversal 위험이 있는 ZIP member는 저장하지 말라. 깨진 ZIP은 기존 파일을 유지하고 오류 정보를 남기되, 정상 ZIP은 원본 ZIP을 삭제하여 `tran` parquet 변환에도 ZIP 원본이 들어가지 않게 하라. DART 설정은 상세 화면에서 다운로드 팝업을 열고 팝업 내부 다운로드 링크를 클릭하는 방식으로 조정하라.

## 변경 파일

- `crawler_app/workflow.py`
- `configs/dart.json`
- `docs/push-history/20260604_144922_codex-advancement-latest-dedupe-20260528_DART-ZIP-압축해제-산출물-정리.md`

## 변경 이유

DART는 상세 문서 다운로드 시 PDF 단일 파일뿐 아니라 ZIP 압축본을 반환한다. 기존 구조는 ZIP 원본을 그대로 `filter` 산출물로 남기고, `tran`에서도 `.zip.parquet`으로 보존했다. 운영자가 실제로 확인해야 하는 것은 ZIP 컨테이너 자체가 아니라 내부 HTML, 이미지, PDF 등 실제 문서 파일이므로, ZIP을 해제하여 내부 파일만 수집 산출물로 남기는 쪽이 저장소 탐색과 후속 데이터 변환에 더 적합하다.

DART 설정도 기존 본문 `extract_body` 방식으로는 상세 콘텐츠 구조를 안정적으로 수집하기 어렵다. DART 상세 페이지의 실제 문서는 iframe과 다운로드 팝업을 거쳐 제공되므로, 설정은 다운로드 버튼 클릭 후 팝업 내부 다운로드 링크를 클릭하는 방식으로 정리했다.

## 설계 판단

- ZIP 해제는 사이트별 예외가 아니라 공통 `action=download` 후처리에 추가했다.
- 정상 ZIP은 원본을 삭제하고 내부 파일만 `downloaded_files`에 기록한다.
- 내부 파일은 ZIP 내부 폴더 구조를 보존하지 않고 평탄화한다.
- 내부 파일명 앞에는 `record_key`를 붙인다. 이로써 `DART-...`, `MOTIR-...` 등 기존 record key 양식과 맞춰진다.
- ZIP 내부 member가 `../`, 절대경로, 드라이브 경로처럼 위험한 형태이면 저장하지 않는다.
- 깨진 ZIP 또는 해제 가능한 파일이 없는 ZIP은 기존 동작을 보존해 원본 ZIP을 남기고 `zip_extract_error`를 step log에 기록한다.

## 보류한 대안

- ZIP 원본과 내부 파일을 모두 보존하는 방식은 저장량이 늘고 `tran`에 중복 parquet이 생기므로 제외했다.
- ZIP 내부 폴더 구조 보존 방식은 사용자가 원치 않았고, 운영자가 파일을 한 위치에서 확인하기 어렵기 때문에 제외했다.
- DART 전용 코드 분기는 기존 JSON config 기반 공통 크롤러 구조를 흔들 수 있어 제외했다.

## 검증 결과

- `.\.venv\Scripts\python.exe -m unittest tests.test_workflow.WorkflowDownloadTests.test_download_extracts_browser_zip_and_removes_archive tests.test_workflow.WorkflowDownloadTests.test_download_extracts_response_zip_with_flattened_unique_names tests.test_workflow.WorkflowDownloadTests.test_download_zip_skips_unsafe_members tests.test_workflow.WorkflowDownloadTests.test_download_keeps_invalid_zip_as_original_file`
  - 결과: 통과
- `.\.venv\Scripts\python.exe -m compileall crawler_app\workflow.py tests\test_workflow.py`
  - 결과: 통과
- `git diff --check -- crawler_app\workflow.py tests\test_workflow.py`
  - 결과: 통과
- DART smoke 실행
  - 결과: 성공
  - 확인 내용:
    - ZIP 원본 파일 없음
    - ZIP 전용 하위 폴더 없음
    - 내부 파일이 `downloads/YYYYMMDD` 바로 아래에 `DART-LEDZDO6CYRATW_파일명` 형태로 저장됨
    - `tran` 변환 정상 생성

## 의도적으로 제외한 파일

- `configs/구글.json`: 이번 DART/ZIP 작업 범위 밖 변경
- `configs/다음.json`: 이번 DART/ZIP 작업 범위 밖 변경
- `crawler_app/workflow_records_rollup.py`: 이번 DART/ZIP 작업 범위 밖 변경
- `tests/test_workflow.py`: ZIP 검증용 테스트 변경이 있으나, 현재 팀 push 규칙상 테스트 파일은 기본적으로 versioning 대상에서 제외
- `imsi/`, `outputs/`, `logs/`, `runtime/`, `orchestration_state/`, `.env`, `.venv/`: 로컬 실행/검증/비밀값 산출물

## 남은 리스크

- ZIP 내부 파일명이 CP949 등 다른 encoding으로 저장된 경우 Python zipfile의 해석 결과에 영향을 받을 수 있다.
- 중첩 ZIP은 이번 변경에서 재귀 해제하지 않고 내부 파일 하나로 취급한다.
- DART 상세 페이지의 다운로드 팝업 구조가 바뀌면 설정 XPath는 다시 조정해야 한다.
