# workflow records, rollup, API, storage 개선

- 작성 시각: 2026-05-29 19:02:27 KST
- 저장소 경로: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- 브랜치: `codex/advancement-latest-dedupe-20260528`
- 원격 대상: `origin/codex/advancement-latest-dedupe-20260528`
- 커밋 메시지: `workflow records rollup api storage 개선`

## 요청 / 프롬프트 흐름

이번 push는 2026-05-29에 이어진 workflow 기록, 중복 진단, rollup, parquet 변환, REST API, 서버 기반 rollup 실행 요청을 하나의 변경 흐름으로 병합해 정리한다.

병합된 원본 요청은 `prompts/20260529_workflow-records-rollup-api-storage-merged.md`에 기록했다. 개별 임시 프롬프트 파일은 push 혼선을 막기 위해 병합본으로 대체했다.

핵심 요청은 다음과 같다.

- 중복 진단 기준을 `final_url` 중심으로 통일한다.
- API형 수집 결과도 workflow 기록에서는 기사 URL을 `final_url`로 남긴다.
- `workflow_records.json` record 구조를 필요한 메타데이터 중심으로 정리한다.
- `latest.json`을 생성하여 이후 중복 진단 boundary로 사용한다.
- nonfilter 폴더는 제거하되 nonfilter 최신 boundary는 `latest.json`에 남긴다.
- `workflow_records.json` line-count 제한 대신 지정 시간 rollup archive로 이동한다.
- rollup archive는 `outputs/<crawler>/filter/rollup/`에 저장하고 최대 20개만 유지한다.
- rollup과 workflow 저장은 같은 file lock으로 동시 쓰기 충돌을 막는다.
- API형을 제외한 filter 산출물은 `tran` 폴더에 parquet으로 변환한다.
- parquet 변환은 모든 파일 형식을 binary row로 보존하되 `latest.json`은 제외한다.
- workflow records 조회용 POST API를 추가한다.
- Windows Task Scheduler 기반 rollup 등록 코드는 제거하고, 웹 서버 실행 중 Python background scheduler가 지정 시간 rollup을 수행하게 한다.

## 변경한 파일

- `.gitignore`
- `README.md`
- `configs/구글.json`
- `crawler_app/duplicate_keys.py`
- `crawler_app/file_lock.py`
- `crawler_app/orchestration.py`
- `crawler_app/web.py`
- `crawler_app/windows_scheduler.py`
- `crawler_app/workflow.py`
- `crawler_app/workflow_records_api.py`
- `crawler_app/workflow_records_rollup.py`
- `crawler_app/workflow_records_rollup_scheduler.py`
- `requirements.txt`
- `scripts/Stop-OrchestrationJobs.ps1`
- `prompts/20260529_workflow-records-rollup-api-storage-merged.md`
- `docs/push-history/20260529_190227_codex-advancement-latest-dedupe-20260528_workflow-records-rollup-api-storage.md`

## 변경 이유

기존 구조는 `workflow_records.json`이 계속 누적되며 커질 수 있고, rollup 후 live record가 제거되면 이후 중복 진단이 약해질 수 있었다. 또한 API형과 일반 사이트형의 URL 저장 방식, parser item 저장 방식, filter/nonfilter 저장 방식이 서로 다르게 보이는 문제가 있었다.

이번 변경은 다음 운영 요구를 맞추기 위한 것이다.

- workflow 기록은 데이터 저장소 조회용 메타데이터로 쓰일 수 있어야 한다.
- 중복 진단은 제목이 아니라 URL 기준이어야 한다.
- rollup 후에도 오늘/live 데이터와 과거/rollup 데이터 조회 경로가 명확해야 한다.
- 수집 산출물은 parquet 변환으로 후속 데이터 처리에 넘길 수 있어야 한다.
- rollup은 별도 Windows task가 아니라 크롤러 서버가 살아 있을 때 자동 수행되어야 한다.

## 설계 판단

### final_url 기준 중복 진단

`title`, `title + url`, `detail_url` 계열 fallback을 중복 기준에서 제거하고 `final_url` 기준으로 통일했다. 같은 제목이 다른 기사일 수 있고, 제목이 조금 달라도 같은 URL이면 같은 기사일 수 있기 때문이다.

API형 수집 결과는 원천 API가 `detail_url`, `originallink`, `link` 같은 필드를 제공하지만, workflow 기록에서는 기사 URL을 `final_url`로 정규화하는 방향을 유지한다.

### latest.json boundary

`latest.json`은 이후 중복 진단을 위한 작은 boundary 파일이다. 검색어/필터별 `search_term`, `filter_term`, `final_url`, `pub_date`를 남긴다.

숫자형 검색어는 페이지 파라미터로 보고 filter group 기준으로 boundary를 사용한다. 일반 검색어는 search term group을 유지한다. 같은 실행 안에서 다른 검색어가 이미 수집한 URL과 겹치면 수집 중단이 아니라 item skip으로 처리한다.

API형에서는 같은 검색어/필터 그룹의 최신 `pub_date`가 같은 기사가 여러 개 있을 수 있으므로, 같은 최신 `pub_date` record를 모두 `latest.json`에 남긴다.

### rollup

line-count 기반 trimming은 제거했다. 대신 지정 시간에 `workflow_records.json`을 `filter/rollup/workflow_records_YYYYMMDD_HHMMSS.json`으로 이동한다. archive는 최신순 정렬 후 저장하며, 각 위치마다 20개까지만 유지한다.

rollup과 workflow 저장은 같은 file lock을 공유한다. 크롤링 도중 rollup이 같은 파일을 건드리는 상황을 줄이기 위한 선택이다.

### Python 서버 기반 rollup

기존 Windows Task Scheduler rollup 등록 코드는 제거했다. rollup은 웹 서버가 켜져 있을 때 `crawler_app.workflow_records_rollup_scheduler.WorkflowRecordsRollupScheduler`가 Python background thread로 실행한다.

롤링 시간은 `crawler_app/workflow_records_rollup.py`의 `DEFAULT_ROLLUP_TIME`에서 설정한다. 값을 바꾼 뒤에는 서버를 재시작해야 적용된다.

### parquet 변환

일반 사이트형 crawler는 `filter` 산출물을 `tran` 폴더에 parquet으로 변환한다. 파일 형식별 텍스트 파싱 대신 모든 파일을 binary row로 보존한다. 원본 파일 손실이나 포맷별 누락 위험을 줄이기 위한 판단이다.

API형 `naver_news`, `daum`, `google`은 parquet 변환 대상에서 제외했다. `latest.json`도 변환 대상에서 제외한다.

## Workflow Records API 사용법

workflow records 조회 API는 현재 및 rollup된 `workflow_records.json` record를 POST로 조회한다. 응답 item은 별도 가공 DTO가 아니라 현재 workflow record 구조를 그대로 따른다.

### Endpoint

```text
POST /api/workflow-records
POST /api/workflow-records/search
```

두 endpoint는 같은 기능이다.

### 기본 요청 예시: 오늘 live 데이터 조회

오늘 날짜를 조회하면 rollup archive가 아니라 live 파일인 `outputs/<source_name>/filter/workflow_records.json`을 읽는다.

```json
{
  "date": "2026-05-29",
  "source_name": "naver_news",
  "page": 1,
  "page_size": 20,
  "sort_by": "pub_date",
  "sort_order": "desc"
}
```

### 과거 rollup 조회 예시

오늘이 아닌 날짜를 조회하면 `outputs/<source_name>/filter/rollup/workflow_records_YYYYMMDD_HHMMSS.json` 파일 중 해당 날짜 archive를 읽는다.

```json
{
  "date": "2026-05-28",
  "source_name": "naver_news",
  "page": 1,
  "page_size": 20
}
```

### 날짜 범위 조회 예시

`from_date`와 `to_date`를 사용하면 여러 날짜의 rollup archive와 오늘 live 파일을 함께 조회할 수 있다.

```json
{
  "from_date": "2026-05-01",
  "to_date": "2026-05-29",
  "page": 1,
  "page_size": 50,
  "sort_by": "pub_date",
  "sort_order": "desc"
}
```

### source_name 생략

`source_name`을 생략하면 `outputs/*/filter` 아래 모든 source를 대상으로 조회한다.

```json
{
  "date": "2026-05-29",
  "page": 1,
  "page_size": 20
}
```

### 파라미터

| 필드 | 의미 |
|---|---|
| `date` | 단일 날짜 조회. `YYYY-MM-DD` 형식 |
| `from_date` | 범위 시작 날짜. `YYYY-MM-DD` 형식 |
| `to_date` | 범위 종료 날짜. `YYYY-MM-DD` 형식 |
| `source_name` | `outputs/<source_name>` 폴더명. 예: `naver_news`, `signal`, `motir_news` |
| `page` | 페이지 번호. 기본값 1 |
| `page_size` | 페이지 크기. 기본값 20, 최대 100 |
| `sort_by` | 정렬 필드. 기본값 `pub_date`, `published_at` alias 허용 |
| `sort_order` | `desc` 또는 `asc`. 기본값 `desc` |

`date`와 `from_date`/`to_date`를 동시에 쓰지 않는 것을 권장한다.

### 참조 API 시트와 현재 구현 매핑

개발팀이 전달한 참조 API 시트는 `user_id`, `read_status`, `favorite_status`, `is_read`, `is_favorite`, `is_major` 같은 사용자 상태 필드를 포함한다. 현재 구현은 별도 DB나 사용자 상태 저장소를 만들지 않고 `workflow_records.json` 및 rollup archive에 실제로 존재하는 값만 반환한다.

| 참조 API 필드 | 현재 구현 |
|---|---|
| `user_id` | 현재 workflow record에는 사용자별 데이터가 없으므로 필터링에 사용하지 않음 |
| `page`, `page_size` | 지원 |
| `sort_by=published_at` | `pub_date` alias로 처리 |
| `sort_order=desc/asc` | 지원 |
| `read_status`, `favorite_status` | 현재 workflow record에 상태값이 없으므로 적용하지 않음 |
| `article_id` | 별도 변환하지 않고 `record_key`를 반환 |
| `title` | `extract_title`로 반환 |
| `source_name` | `outputs/<source_name>` 폴더명을 기준으로 조회하고, 응답 item에는 원본 record 구조를 유지 |
| `published_at` | 별도 필드명 변환 없이 `pub_date`를 반환 |
| `url` | 별도 필드명 변환 없이 `final_url`을 반환 |
| `is_major`, `is_read`, `read_at`, `is_favorite`, `favorite_at` | 현재 데이터에 없으므로 반환하지 않음 |

즉, 이번 API는 참조 시트의 UX 흐름을 참고하되, 응답 item은 현재 크롤러의 source of truth인 workflow record 구조 그대로 반환하는 조회 API다. 사용자 상태값이 필요해지면 별도 상태 저장소나 record 확장 정책을 먼저 정해야 한다.

### 조회 파일 선택 규칙

API는 날짜 조건에 따라 읽을 파일을 다르게 선택한다.

| 조회 조건 | 읽는 파일 |
|---|---|
| `date`가 오늘 날짜 | `outputs/<source_name>/filter/workflow_records.json` |
| `date`가 과거 날짜 | `outputs/<source_name>/filter/rollup/workflow_records_YYYYMMDD_HHMMSS.json` |
| `from_date`/`to_date`가 오늘을 포함 | 과거 날짜는 rollup archive, 오늘은 live `workflow_records.json` |
| `source_name` 없음 | `outputs/*/filter` 아래 source 전체를 순회 |

rollup archive가 없는 과거 날짜는 조회 결과가 비어 있을 수 있다. 이는 실패가 아니라 해당 날짜의 rollup 파일이 아직 존재하지 않는 상태다.

### 응답 필드 의미

현재 workflow record의 기본 응답 item은 아래 필드를 중심으로 구성된다.

| 필드 | 의미 |
|---|---|
| `record_key` | crawler prefix와 URL fingerprint 기반 고유 record id |
| `search_term` | 수집 당시 적용된 검색어. 페이지 파라미터형 crawler에서는 숫자 문자열일 수 있음 |
| `filter_term` | 필터 매칭값. nonfilter boundary는 `nonfilter`로 기록될 수 있음 |
| `extract_title` | 수집 제목 |
| `description` | API형은 요약/본문 설명, 일반 사이트형은 없으면 빈 문자열 |
| `pub_date` | API형은 원문 발행일, 일반 사이트형은 수집 시각 기반 fallback |
| `final_url` | 중복 진단과 외부 조회에 사용하는 최종 기사 URL |

응답은 `totalCount`, `page`, `pageSize`, `items` 구조로 감싸서 반환한다. `items` 내부는 record 원본 구조를 유지한다.

### 오류 및 검증 포인트

- 잘못된 날짜 형식은 명확한 오류로 처리해야 한다.
- `page`와 `page_size`는 양수 기준으로 처리한다.
- `page_size`는 과도한 응답을 막기 위해 최대값을 둔다.
- `sort_by=published_at`은 참조 API 시트 호환을 위해 `pub_date`로 해석한다.
- secret, SMTP password, API key는 응답과 로그에 포함하지 않는다.

### 응답 예시

```json
{
  "totalCount": 2,
  "page": 1,
  "pageSize": 20,
  "items": [
    {
      "record_key": "NAVER-HN3QWWSTBIRN2",
      "search_term": "SK",
      "filter_term": "SK",
      "extract_title": "SK하이닉스 2배 ETF, 홍콩 시장 8.5% 장악…반도체 레버리지 광풍",
      "description": "기사 요약 또는 본문 일부",
      "pub_date": "Fri, 29 May 2026 18:26:00 +0900",
      "final_url": "https://www.newspim.com/news/view/20260529001149"
    }
  ]
}
```

### PowerShell 호출 예시

```powershell
$body = @{
  date = "2026-05-29"
  source_name = "naver_news"
  page = 1
  page_size = 20
  sort_by = "pub_date"
  sort_order = "desc"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:3000/api/workflow-records" `
  -ContentType "application/json" `
  -Body $body
```

### curl 호출 예시

```bash
curl -X POST "http://127.0.0.1:3000/api/workflow-records" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-05-29","source_name":"naver_news","page":1,"page_size":20}'
```

### 브라우저에서 확인하는 방법

이 API는 POST API라 주소창에 URL만 입력해서는 정상 요청을 만들기 어렵다. 브라우저에서 직접 확인하려면 개발자 도구 Console에서 아래처럼 호출한다.

```javascript
fetch("http://127.0.0.1:3000/api/workflow-records", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    date: "2026-05-29",
    source_name: "naver_news",
    page: 1,
    page_size: 20
  })
}).then(r => r.json()).then(console.log)
```

### 제약과 남은 확인 사항

- read/favorite/is_major 같은 사용자 상태 필드는 아직 workflow record에 없으므로 응답하지 않는다.
- 오늘 날짜는 live `workflow_records.json` 기준이다. 해당 파일이 rollup되어 사라진 직후에는 오늘 live 조회 결과가 줄어들 수 있다.
- 과거 날짜 조회는 rollup archive가 존재해야 가능하다.

## 검증 결과

실행한 검증:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_workflow_records_rollup tests.test_workflow_records_rollup_scheduler tests.test_windows_scheduler
.\.venv\Scripts\python.exe -m unittest tests.test_web tests.test_workflow_records_api
.\.venv\Scripts\python.exe -m unittest tests.test_workflow tests.test_orchestration
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall crawler_app tests
```

결과:

- rollup/scheduler 관련 테스트 통과
- web/API 관련 테스트 통과
- workflow/orchestration 관련 테스트 통과
- 전체 테스트 217개 이상 통과
- compileall 통과

## 의도적으로 제외한 파일

다음은 로컬 검증 또는 런타임 산출물이므로 stage하지 않는다.

- `tests/` 변경 파일: validation-only 자산으로 제외
- `outputs/`
- `runtime/`
- `logs/`
- `orchestration_state/`
- `.env`, `.venv/`
- `naver_news_문제_18시26분_SK하이닉스 2배 ETF/`

## 남은 리스크

- API형에서 이미 rollup된 과거 URL을 `latest.json`만으로 모두 기억하지 못하는 케이스가 확인되었다. 다음 수정에서는 API형 `latest.json`에 검색어 그룹을 유지하면서도 최근 URL index를 추가하는 방향을 검토한다.
- 서버 기반 rollup은 서버가 켜져 있을 때만 실행된다. 서버가 지정 시간에 꺼져 있으면 해당 시점 rollup은 실행되지 않는다.
- rollup 시간이 변경되면 서버 재시작이 필요하다.

## Push 계획

선택적으로 stage할 파일:

- source/runtime files
- config/doc files
- 병합 prompt record
- 이 push history record

stage하지 않을 파일:

- tracked test file modifications
- local runtime/output/secret files

예정 push:

```powershell
git push origin codex/advancement-latest-dedupe-20260528
```
