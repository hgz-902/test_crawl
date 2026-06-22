# Parquet 전환 메뉴 추가

- 일시: 2026-06-22 15:47 KST
- 브랜치: `dev/crawler-tran`
- 대상: UI 상단 메뉴, FastAPI route, parquet 원본 다운로드 변환

## 목적

운영자가 `outputs/*/tran/*.parquet` 파일을 브라우저에서 확인하고, 원본 파일로 즉시 다운로드할 수 있게 한다.

## 변경 내용

- 상단 메뉴에 `parquet 전환` 링크를 추가했다.
- `/parquet-converter`에서 `outputs/<항목>/tran/*.parquet` 목록을 보여준다.
- 단일 `전환` 버튼은 parquet row의 `content_bytes`를 원본 파일명으로 다운로드한다.
- 선택 `ZIP 다운로드`는 선택한 parquet들을 원본 파일로 변환해 zip으로 내려준다.
- `metadata_*.parquet`은 원본 `workflow_records`와 매칭용 `tran_manifest`를 함께 포함한 JSON으로 다운로드한다.
- 경로 접근은 `outputs/<name>/tran/*.parquet` 상대경로로 제한하고, 절대경로와 `..` 접근을 차단한다.

## 설계 판단

- 기존 `filter` 파일을 다시 내려주는 방식이 아니라 parquet 자체를 읽어 전환한다.
- 서버에 복원 파일을 생성하지 않고 요청 시 메모리에서 변환해 응답한다.
- metadata 전환 결과에는 원본 기록뿐 아니라 parquet와 원본 파일 매칭 정보도 보존한다.

## 검증

- `python -m compileall crawler_app`
- `python -m unittest tests.test_web -v`
- `python -m unittest tests.test_tran_parquet_export -v`
- `node --check static/app.js`
- 임시 서버 `/parquet-converter`에서 목록, 단일 다운로드, 선택 ZIP 다운로드 확인

## 남은 위험

- 매우 큰 parquet 파일을 다량 선택해 ZIP으로 묶을 경우 메모리 사용량이 커질 수 있다.
