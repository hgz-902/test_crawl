# Crawler Orchestrator

사이트별로 분리된 크롤러를 공통 오케스트레이터에서 실행하고, 실행 결과를 로그로 남기는 기본 구조입니다.

## 구조

- `crawlers/`: JSON 워크플로우 크롤러 래퍼
- `crawler_app/base.py`: 공통 크롤러 인터페이스와 결과 모델
- `crawler_app/orchestrator.py`: 크롤러 자동 발견 및 실행
- `crawler_app/document_extractors.py`: PDF/HWPX 첨부파일 텍스트 추출 공통 모듈
- `logs/orchestrator.log`: 텍스트 로그
- `logs/crawl_results.jsonl`: 크롤러별 실행 결과 JSONL 로그

## 실행

```bash
pip install -r requirements.txt
python main.py
python main.py --crawler configurable --config "configs/기후에너지환경부_보도자료.json"
uvicorn crawler_app.web:app --reload
python -m uvicorn crawler_app.web:app --reload --host 127.0.0.1 --port 3000
```

## JSON 설정 기반 크롤러

`configurable` 크롤러는 사이트별 Python 코드를 새로 만들지 않고 JSON 설정 파일에 URL과 DOM 선택 규칙을 정의해서 실행합니다.

```bash
python main.py --crawler configurable --config "configs/기후에너지환경부_보도자료.json"
```

설정 파일은 아래 정보를 관리합니다.

- `start_url`: 목록 페이지 URL. `{search_term}`를 넣으면 검색어별로 다른 주소를 만들 수 있다.
- `base_url`: 상대 URL을 절대 URL로 바꿀 때 사용할 기준 URL
- `output_dir`: 다운로드 원본, 추출 텍스트, 메타데이터 저장 위치
- 저장 파일명에는 `record_key` prefix가 붙고, 결과 스냅샷(`workflow_records.json`)으로 레코드와 파일의 매핑을 추적할 수 있다.
- `filter_terms`가 있으면 결과는 `output_dir/filter` 와 `output_dir/nonfilter` 로 분리 저장된다. 필터가 없으면 전체 결과를 `output_dir/filter` 에 저장한다.
- `notes`: 해당 크롤러의 특이사항, 예외 처리 메모, xpath 주의점
- `search_terms`: 여러 검색어를 순차 실행할 때 사용할 검색어 목록
- `filter_terms`: 수집이 끝난 뒤 결과 레코드 전체에서 한 번만 적용할 필터 키워드 목록
- `steps[].action = parser`: RSS 같은 구조화 응답을 파싱하는 step
- `steps[].attr = google`: `parser` step에서 Google News RSS 파서를 선택한다.
- `steps[].attr = naver`: `parser` step에서 Naver News Search API 파서를 선택한다.
- `parser` step에서는 `xpath`, `open_mode`, `wait_state`, `loop` 관련 필드를 사용하지 않는다.
- `steps[0].loop`: 목록/반복 영역을 시작하는 step 반복 사용 여부. 켜면 `xpath` + `xpath_2` 두 앵커를 입력하며, `loop_limit`를 비우면 최대까지 반복한다.
- `steps[0].xpath`: 반복 DOM 내부에서 실행할 첫 번째 단계 XPath
- `steps[].loop`: step 단위 반복 사용 여부. 2번 이후 step에서 켜면 현재 페이지 안의 반복 요소를 순회한다. `xpath` + `xpath_2` 두 앵커를 입력하며, `loop_limit`를 비우면 최대까지 반복한다.
- `steps[].loop_limit`: 반복 step의 최대 횟수. 비우면 `max until first miss`
- `download` step: XPath가 여러 요소에 매칭되면 각 요소를 순회하며 모두 다운로드
- 필터는 실행이 모두 끝난 뒤 레코드 단위로 한 번만 적용하며, 매칭 결과는 `filter`, 비매칭 결과는 `nonfilter` 아래에 별도 저장된다.
- `list`: 목록 item selector와 제목/날짜/상세 URL 생성 규칙
- `detail`: 상세 페이지의 본문/담당부서/연락처/첨부파일 selector

DOM 선택 규칙은 CSS selector와 XPath를 모두 지원합니다.

```json
{
  "selector": {
    "type": "css",
    "value": "h3 a"
  },
  "attr": "text"
}
```

```json
{
  "selector": {
    "type": "xpath",
    "value": ".//li[span[contains(text(), '담당부서')]]"
  },
  "attr": "text",
  "regex": "담당부서\\s*(.+)"
}
```

지원하는 주요 필드 옵션은 다음과 같습니다.

- `attr: "text"`: 선택된 요소의 텍스트 추출
- `attr: "html"`: 선택된 요소의 HTML 원문 추출
- `attr: "href"` 같은 속성명: HTML attribute 추출
- `regex`: 추출값에서 첫 번째 capture group 사용
- `template`: 앞서 추출된 필드값으로 값 생성
- `urljoin: true`: 상대 URL을 `base_url` 기준 절대 URL로 변환
- `date_format`: 날짜 문자열을 날짜로 파싱
- `html_to_text: true`: HTML 문자열을 텍스트로 변환
- `scope: "document"`: 상세 컨테이너가 아니라 문서 전체에서 selector 실행

### Naver News API 예시

Naver News Search API는 환경변수 `NAVER_CLIENT_ID`와 `NAVER_CLIENT_SECRET`가 필요합니다.
루트의 `.env.example` 를 참고해 `.env` 파일을 만들면 자동으로 읽습니다.
Naver API parser는 UI와 CLI 모두에서 안전한 실행 범위를 요구합니다. `page_limit`은 최대 10, `loop_limit`은 1~100 사이로 명시해야 합니다.

```bash
python main.py --crawler configurable --config "configs/네이버.json"
```

```json
{
  "name": "네이버뉴스",
  "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=20&start=1&sort=date",
  "output_dir": "outputs/naver_news",
  "search_terms": ["SK이노베이션", "최태원", "유가전망"],
  "steps": [
    {
      "name": "naver_news_api",
      "action": "parser",
      "attr": "naver",
      "page_limit": 1,
      "loop_limit": 20
    }
  ]
}
```

## 첨부파일 텍스트 추출

공통 모듈로 PDF와 HWPX 파일에서 텍스트를 추출할 수 있습니다.

```python
from crawler_app.document_extractors import extract_text_from_bytes

attachment_bytes = download_attachment_somehow()
extract_result = extract_text_from_bytes(
    file_bytes=attachment_bytes,
    file_type="hwpx",
    file_name="press_release.hwpx",
    source_url="https://example.com/file.hwpx",
)

if extract_result.success:
    attachment = {
        "file_name": extract_result.file_name,
        "file_type": extract_result.file_type,
        "text": extract_result.text,
        "text_length": extract_result.text_length,
    }
else:
    attachment = {
        "file_name": extract_result.file_name,
        "file_type": extract_result.file_type,
        "error": extract_result.error,
    }
```

`DocumentExtractResult`는 아래 정보를 공통으로 반환합니다.

- `success`: 추출 성공 여부
- `text`: 추출된 본문 텍스트
- `text_length`: 추출된 텍스트 길이
- `page_count`: PDF 페이지 수
- `metadata`: 추출 과정 메타데이터
- `error`: 실패 사유

주의사항:

- PDF 추출은 `pypdf` 의존성이 필요합니다.
- 현재 PDF는 텍스트 레이어가 있는 파일만 지원합니다.
- 구형 `hwp`는 아직 지원하지 않고 `hwpx`만 지원합니다.

## Batch crawler jobs

The web app includes an in-app async scheduler at `/jobs`.

- Choose which existing `configs/*.json` files should run automatically.
- Set an interval in minutes for each selected config. Values below 5 minutes are clamped to 5 minutes.
- Use `Run now` to execute a configured job manually.
- Last run, next run, status, item count, and error/message fields are persisted in `crawler_jobs.json`.
- The scheduler runs inside the FastAPI process with per-job locking and a small global concurrency cap. Do not use Windows Task Scheduler for this flow unless that is approved as a separate operating-system scheduling slice.

Completion email is sent to `bloodknihts@gmail.com` after scheduled and `/jobs` manual runs only when email is explicitly enabled and SMTP environment variables are configured. If email is disabled or SMTP is not configured, email is skipped without failing the crawl.

Required SMTP variables:

```bash
CRAWLER_COMPLETION_EMAIL_ENABLED=1
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_FROM=crawler@example.com
SMTP_USERNAME=your_smtp_username
SMTP_PASSWORD=your_smtp_password
SMTP_USE_TLS=true
```
