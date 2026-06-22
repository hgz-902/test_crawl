# Parser item JSON 파일명 규칙 변경

- Date/Time: 2026-05-20 11:35:52 KST
- Repository: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- Branch: `dev/crawler-current`
- Remote target: `origin dev/crawler-current` (`https://github.com/K-Ternag/crawlService.git`)
- Commit message: `Parser item JSON 파일명 규칙 변경`
- Push command: `git push origin dev/crawler-current:dev/crawler-current`

## 요청 작업 / Slice

네이버뉴스, 다음, 구글 parser/API형 크롤러의 item별 JSON 파일명이 기존 hash/code 형태라 사람이 구분하기 어려웠다. 다른 크롤러 저장 구조는 유지하면서, 세 parser 저장 함수만 사람이 읽을 수 있는 provider/timestamp/순번 규칙으로 변경했다.

## 변경 파일

- `crawler_app/naver_news_api.py`
- `crawler_app/daum_news_api.py`
- `crawler_app/google_news_rss.py`
- `tests/test_naver_news_api.py`
- `tests/test_daum_news_api.py`
- `tests/test_google_news_rss.py`
- `tests/test_workflow.py`
- `prompts/20260520_112719_parser_item_filename_rule.md`

## 변경 이유

- `item_<hash>.json` 파일명은 사람이 파일 목록만 보고 source, 수집 시각, 같은 batch 내 순서를 판단하기 어렵다.
- 운영자가 outputs를 직접 확인할 때 provider와 수집 시각이 드러나는 파일명이 필요했다.
- 파일명에 기사 제목을 넣으면 길이, 특수문자, OS 호환성 문제가 생길 수 있으므로 제목 기반 파일명은 배제했다.

## 설계 판단 및 Tradeoff

- 새 파일명은 `NAVER_YYYYMMDD_HHMISS_n.json`, `DAUM_YYYYMMDD_HHMISS_n.json`, `GOOGLE_YYYYMMDD_HHMISS_n.json` 형식을 사용한다.
- `YYYYMMDD`와 `HHMISS`는 저장 함수 호출 시 한국 시간 기준으로 한 번 계산한다. 같은 batch 안의 item은 같은 timestamp를 공유하고, 순번만 `1, 2, 3...`으로 증가한다.
- 기존 `items/YYYYMMDD/` 날짜 폴더 구조는 유지했다. 따라서 run suffix 폴더인 `YYYYMMDD_1`, `YYYYMMDD_2`는 만들지 않는다.
- hash 파일명은 같은 item에 대해 overwrite-safe한 장점이 있었지만, 사람 가독성이 낮았다. 이번 변경은 운영 확인성을 우선한다.
- 중복 판정은 파일명이 아니라 record의 title/url/post_id/detail_url/originallink 계열 중복 key를 사용하므로, 파일명 변경이 중복 판단을 깨지 않도록 했다.

## 구현 요약

- `crawler_app/naver_news_api.py`
  - `item_<hash>.json` 생성 제거.
  - `NAVER_<date>_<time>_<index>.json` 생성 추가.
- `crawler_app/daum_news_api.py`
  - `DAUM_<date>_<time>_<index>.json` 생성 추가.
- `crawler_app/google_news_rss.py`
  - `GOOGLE_<date>_<time>_<index>.json` 생성 추가.
- 세 parser 모두 item별 JSON 분리 저장과 manifest의 `item_files` 상대경로를 유지했다.
- workflow record의 `output_file`은 manifest `item_files`를 통해 실제 item JSON 경로로 연결된다.

## 검증 결과

- `.\.venv\Scripts\python.exe -m unittest tests.test_naver_news_api tests.test_google_news_rss tests.test_daum_news_api tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_naver_news_api_without_playwright tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_daum_news_api_without_playwright tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_google_news_rss_without_playwright tests.test_workflow.WorkflowDownloadTests.test_run_workflow_config_parses_google_news_rss_without_search_terms_uses_indexed_dir tests.test_workflow.WorkflowDownloadTests.test_parser_duplicate_stop_applies_to_current_search_term_only tests.test_workflow.WorkflowDownloadTests.test_duplicate_stop_without_new_records_is_not_no_items_error`
  - Result: PASS, 23 tests OK
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
  - Result: PASS, 174 tests OK
- 임시 저장 smoke:
  - `items/20260520/NAVER_20260520_113108_1.json`
  - `items/20260520/NAVER_20260520_113108_2.json`
  - `items/20260520/NAVER_20260520_113108_3.json`
  - `items/20260520/DAUM_20260520_113108_1.json`
  - `items/20260520/DAUM_20260520_113108_2.json`
  - `items/20260520/DAUM_20260520_113108_3.json`
  - `items/20260520/GOOGLE_20260520_113108_1.json`
  - `items/20260520/GOOGLE_20260520_113108_2.json`
  - `items/20260520/GOOGLE_20260520_113108_3.json`
- workflow smoke:
  - `workflow_records.json`의 `output_file`이 실제 생성된 `NAVER_...`, `DAUM_...`, `GOOGLE_...` 파일과 일치하고 파일 존재 확인.

## Ignore Hygiene / 제외 파일

- `.env`, `.venv/`, `outputs/`, `orchestration_state/`, `runtime/`, `logs/`, `qa-artifacts/`, `imsi/`, `__pycache__/`는 `.gitignore` 대상이며 staging하지 않았다.
- `configs/네이버뉴스.json`은 작업 전부터 검색어와 loop_limit이 바뀐 dirty file이다. 이번 요청의 파일명 규칙 변경과 직접 관련이 없으므로 stage하지 않는다.

## Secret 점검

- staged 대상에 secret 파일은 포함하지 않는다.
- `.env`, Gmail 앱 비밀번호, SMTP password, Naver/Kakao 실제 key 값은 포함하지 않는다.

## 남은 리스크

- 같은 output_dir에 같은 provider 저장 함수가 같은 초에 두 번 호출되면 파일명이 겹칠 수 있다. 일반 workflow에서는 search term별 output_dir이 다르고 한 batch 내 순번이 안정적이라 문제 가능성은 낮다. 필요하면 후속으로 collision 방어 suffix를 추가할 수 있다.
- 날짜/시간은 한국 시간 기준이다. 다른 timezone 서버에서도 KST로 고정된다.
- 실제 외부 Naver/Kakao/Google 호출은 이번 push 준비 과정에서 수행하지 않았고, mock/smoke로 저장 구조와 workflow 연결을 검증했다.

## Cumulative Prompt / Request Flow

### Current recorded prompt

- Prompt record: `prompts/20260520_112719_parser_item_filename_rule.md`
- Outcome:
  - 네이버/다음/구글 item JSON 파일명을 provider/timestamp/순번 형식으로 변경.
  - 같은 batch 내 `_1`, `_2`, `_3` 순번 검증 추가.
  - `workflow_records.json` output_file 경로 일치 검증 추가.
  - 기존 duplicate stop 테스트로 중복 판정 회귀 확인.

## Commit / Push

- Commit message: `Parser item JSON 파일명 규칙 변경`
- Push command: `git push origin dev/crawler-current:dev/crawler-current`
- Commit hash: pending
- Push result: pending
