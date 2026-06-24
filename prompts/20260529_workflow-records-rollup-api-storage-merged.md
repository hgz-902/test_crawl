# 2026-05-29 workflow records, rollup, API, and storage change prompt

## Consolidated Request

Crawler workflow 기록, 중복 진단, rollup, parquet 변환, workflow_records 조회 API, 서버 기반 rollup 실행 구조를 한 번의 연속 작업으로 정리한다.

### 중복 진단과 URL 기준 정리

- `workflow_records.json`과 `latest.json`의 중복 진단 기준은 `final_url` 중심으로 통일한다.
- 더 이상 `detail_url` 계열을 별도 중복 기준으로 보지 않는다.
- API형 수집 결과라도 외부 저장 및 workflow record에서는 기사 URL을 `final_url`로 기록한다.
- 게시판형 URL이라도 page/query parameter를 임의 제거하지 않는다. 모든 사이트가 같은 final_url 처리 코드를 쓰도록 한다.
- `latest.json` 기반 중복 진단에서는 검색어 그룹을 유지한다.
- 숫자형 검색어는 페이지 파라미터로 보고 필터별 boundary를 기준으로 중단한다.
- 일반 검색어 또는 빈 검색어는 검색어별 boundary를 기준으로 중단한다.
- 동일 실행 내 다른 검색어에서 이미 본 URL은 수집 중단이 아니라 해당 item만 skip한다.
- API형에서는 같은 검색어/필터 그룹 안에서 가장 최신 `pub_date`가 같은 기사가 여러 개면 `latest.json`에 모두 남긴다.
- 검색 중단이든 skip이든 `latest.json`에 남아 있는 모든 URL을 확인한다.

### workflow_records 구조와 record key

- `workflow_records.json`의 각 record는 필요한 필드만 유지한다.
- `extracts` 내부 필드는 record 최상위로 끌어올린다.
- 기본 record 필드는 `record_key`, `search_term`, `filter_term`, `extract_title`, `description`, `pub_date`, `final_url` 중심으로 정리한다.
- API의 `pubDate`는 `pub_date`로 정규화한다.
- 일반 사이트에서 게시일을 수집하지 못하면 수집 시점의 KST RFC2822 형식 날짜를 `pub_date`로 넣는다.
- `record_key`는 crawler prefix와 URL+수집일 기반 blake2b fingerprint로 만든 안정적인 짧은 key를 사용한다.
- 생성된 `record_key`는 item json, text/download 산출물 파일명과 workflow record에 일관되게 반영한다.
- 필터 판정은 record_key, output path 같은 메타데이터가 아니라 실제 콘텐츠 필드만 대상으로 한다.

### latest.json과 nonfilter 정책

- `latest.json`을 `workflow_records.json`과 같은 depth에 생성한다.
- `latest.json`은 이후 중복 진단 boundary에 필요한 `search_term`, `filter_term`, `final_url`, `pub_date`만 저장한다.
- filter에 걸린 최신 record와 nonfilter 최신 record도 boundary로 기록한다.
- nonfilter 폴더 자체는 제거하고, nonfilter 파일은 저장하지 않는다.
- nonfilter에 해당하는 최신 boundary만 `latest.json`에 `filter_term=nonfilter`로 남긴다.

### workflow_records rollup

- `workflow_records.json`의 기존 line-count rolling window는 제거한다.
- workflow_records는 정해진 시간에 rollup archive로 이동한다.
- rollup archive는 `outputs/<crawler>/filter/rollup/workflow_records_YYYYMMDD_HHMMSS.json` 형태로 저장한다.
- rollup 후 원본 `workflow_records.json`은 삭제한다.
- archive는 최신순으로 정렬된 상태로 저장한다.
- 각 위치별 rollup archive는 최대 20개를 유지하고 오래된 파일부터 삭제한다.
- rollup과 workflow_records 저장은 같은 file lock을 사용해 동시에 실행되지 않게 한다.
- 기존 Windows Task Scheduler 기반 rollup 등록 코드는 제거한다.
- 크롤러 웹 서버가 실행 중일 때 Python background scheduler가 지정 시간에 rollup을 수행한다.
- rollup 시간은 `crawler_app/workflow_records_rollup.py`의 `DEFAULT_ROLLUP_TIME`에서 설정한다.

### parquet 변환

- API형인 `naver_news`, `daum`, `google`은 parquet 변환 대상에서 제외한다.
- 그 외 crawler는 `outputs/<crawler>/filter` 아래 파일을 `outputs/<crawler>/tran`에 parquet으로 변환한다.
- 모든 형식(txt, json, pdf, hwp, hwpx, docx 등)을 바이너리 보존형 row로 변환한다.
- `filter/rollup` 안의 rollup archive도 parquet 변환 대상에 포함한다.
- `latest.json`은 parquet 변환 대상에서 제외한다.

### workflow_records 조회 API

- workflow_records를 조회하는 POST API를 추가한다.
- 응답은 현재 `workflow_records.json` record 구조를 그대로 사용한다.
- 오늘 날짜 조회는 live `workflow_records.json`을 읽고, 과거 날짜 조회는 rollup archive를 읽는다.
- `date` 단일 조회와 `from_date`/`to_date` 범위 조회를 모두 지원한다.
- `source_name`, `page`, `page_size`, `sort_by`, `sort_order`를 지원한다.

### 운영 정리

- 오케스트레이션 모니터링 종료는 이 프로젝트의 managed crawler scheduler task를 확실히 삭제해야 한다.
- 서버 내부 Python rollup으로 전환되었으므로 Windows rollup task 등록/launcher 생성 코드는 제거한다.
- 수동 rollup은 PowerShell script 대신 `python -m crawler_app.workflow_records_rollup`으로 수행한다.
- 조사용 산출물과 outputs/runtime/log/secret/test artifacts는 git에 올리지 않는다.
