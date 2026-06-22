# Git Push Change Log - 오케스트레이션 로그 및 중복중단 상태 표시 개선

- Date: 2026-06-01 18:24:28 +09:00
- Repository: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- Branch: `codex/advancement-latest-dedupe-20260528`
- Upstream: `origin/codex/advancement-latest-dedupe-20260528`
- Approved push target: `origin codex/advancement-latest-dedupe-20260528`
- Commit message: `오케스트레이션 로그 및 중복중단 상태 표시 개선`

## Request

오케스트레이션 수동 실행과 Windows Scheduler 예약 실행이 크롤러 설정 페이지의 수동 실행과 동일하게 운영자가 확인 가능한 `logs/crawl_results.jsonl`에 기록되도록 정리한다.

동시에 오케스트레이션 UI에서 `duplicate_stopped` 또는 `duplicated_stopped`가 실패처럼 보이지 않도록 표시 정책을 정리한다. 중복 진단으로 정상 중단된 job은 앱 내부적으로 성공 계열 결과이므로 UI에는 아래처럼 보여야 한다.

```text
앱 최근 상태: 성공
(duplicated_stopped)
```

단, job 또는 batch가 실제 실패한 경우에는 로그나 metadata에 duplicate stop 관련 값이 함께 있더라도 UI에서는 `실패`만 부각한다. 이번 변경은 오케스트레이션/스케줄러 실행 결과 기록과 화면 표시 계층에 한정하며, 개별 크롤러 로직, 사이트별 XPath, 검색어/필터 설정, outputs 저장 구조는 변경하지 않는다.

## Cumulative Prompt / Request Flow

### 1. 오케스트레이션 실행 로그의 운영 확인성 보완

- 요구 배경: 크롤러 설정 페이지에서 수동 실행하면 `logs/crawl_results.jsonl`에 실행 결과가 남지만, 오케스트레이션 수동 실행과 예약 실행은 같은 형식으로 빠르게 확인하기 어려웠다.
- 판단: 별도 `runtime/orchestration-logs` 계층을 새로 키우면 로그 형식이 이원화되고 운영자가 두 경로를 비교해야 한다. 기존 결과 창과 연결된 `crawl_results.jsonl` 양식을 재사용하는 것이 더 단순하고 운영 친화적이다.
- 적용 방향: 오케스트레이션 job 결과를 기존 `CrawlResult` 형태로 변환해 `log_result()`에 넘기고, `crawler_name`만 실행 경로별로 구분한다.
  - 오케스트레이션 페이지 수동 실행: `orchestration_manual`
  - Windows Scheduler 예약 실행: `orchestration_scheduled`

### 2. duplicate stopped 상태 표시 정책 정리

- 요구 배경: 앱 상태가 `duplicate_stopped`일 때 성공/실패 의미가 혼동될 수 있었다.
- 판단: `duplicate_stopped`는 중복 경계를 정상 감지하고 멈춘 성공 계열 결과다. 다만 사용자가 원인을 볼 수 있도록 보조 사유는 남긴다.
- 적용 방향: UI 표시값은 `성공`으로 두고 바로 아래에 `(duplicated_stopped)`를 표시한다. 실제 실패가 있는 경우에는 실패를 우선하여 `실패`만 표시한다.

## Changed Files Included In This Push

```text
crawler_app/orchestration.py
crawler_app/scheduled_runner.py
crawler_app/web.py
templates/orchestration.html
docs/push-history/20260601_182428_codex-advancement-latest-dedupe-20260528_오케스트레이션-로그-및-중복중단-상태-표시-개선.md
```

## Working Tree Files Intentionally Excluded

아래 파일들은 현재 working tree에 변경이 남아 있지만, 이번 push의 운영 코드 변경 범위에서 제외했다. 특히 `tests/` 변경은 이 프로젝트의 push skill 기준상 기본 staging 대상이 아니므로, 검증용/기존 dirty 변경으로 남긴다.

```text
tests/test_orchestration.py
tests/test_scheduled_runner.py
tests/test_web.py
tests/test_windows_scheduler.py
tests/test_workflow.py
```

다음 항목들은 `git status --ignored`에서 ignore 상태로 확인했다.

```text
.env
.venv/
logs/
runtime/
outputs/
orchestration_state/
qa-artifacts/
imsi/
naver_news_문제_18시26분_SK하이닉스 2배 ETF/
tests/test_workflow_records_api.py
tests/test_workflow_records_rollup.py
tests/test_workflow_records_rollup_scheduler.py
```

## Why These Changes Were Made

오케스트레이션 실행은 실제 운영에서 수동 실행보다 더 자주 쓰일 수 있으므로, 실패 원인과 실행 결과가 기존 수동 실행 로그와 같은 곳에 남아야 한다. 기존 설정 페이지 수동 실행은 이미 `CrawlResult -> log_result() -> logs/crawl_results.jsonl` 흐름을 가지고 있었기 때문에, 오케스트레이션도 이 경로를 재사용하면 운영자가 같은 파일만 확인하면 된다.

또한 `duplicate_stopped`는 중복 진단이 성공적으로 동작한 상태인데도 원문 상태값만 노출되면 실패처럼 해석될 수 있다. UI에서는 성공/실패가 먼저 보이고, 중복 중단은 보조 사유로 보이는 것이 운영 판단에 더 적합하다.

## Design Notes And Tradeoffs

### Existing Code Changed Because

- `orchestration.run_batch()`는 job 결과를 만들지만 기존 `crawl_results.jsonl`에는 기록하지 않았다.
- `scheduled_runner.main()`은 예약 실행 결과를 stdout summary로만 출력했고, 크롤러 설정 페이지 수동 실행과 같은 JSONL 로그를 남기지 않았다.
- `templates/orchestration.html`은 `last_status`와 `result.status` 원문을 그대로 표시해 `duplicate_stopped`의 성공 의미를 알기 어려웠다.

### Idea Or Constraint Behind The Change

- 새 로그 파일 체계를 만들지 않고 기존 운영 로그 형식을 재사용한다.
- `crawler_name`만 실행 경로를 구분하는 값으로 바꿔서 기존 로그 소비 방식과 결과 창 의미를 최대한 유지한다.
- 내부 상태값은 바꾸지 않고 UI 표시값만 변환한다.

### Advantages

- 운영자는 `logs/crawl_results.jsonl` 하나로 설정 페이지 수동 실행, 오케스트레이션 수동 실행, 예약 실행 결과를 함께 볼 수 있다.
- 새 runtime 로그 구조를 추가하지 않아 파일 관리와 설명 비용이 줄어든다.
- `duplicate_stopped`는 성공 계열로 표시되어 정상 중복 진단과 실패가 명확히 구분된다.

### Disadvantages Or Costs

- 오케스트레이션 job별 상세 로그 파일을 별도 생성하지 않으므로, 아주 긴 실행 상세를 보려면 기존 JSONL payload와 history/스케줄러 stdout 로그를 함께 봐야 할 수 있다.
- `crawler_name`에 실행 출처가 들어가므로, 실제 config 이름은 `metadata.config_name` 또는 `data` 요약을 함께 확인해야 한다.

### Alternatives Considered Or Deferred

- `runtime/orchestration-logs/YYYYMMDD/<batch_id>/` 아래 batch/job별 `.log`와 `.json`을 만드는 방안: 정보는 풍부하지만 로그 체계가 이원화되어 운영자가 더 복잡하게 느낄 수 있어 이번 push에서는 제외했다.
- UI에서 내부 상태값을 완전히 한글 상태로 치환하는 방안: 내부 상태와 화면 표시가 너무 멀어질 수 있어, `성공`과 `(duplicated_stopped)`를 함께 보여주는 방식으로 절충했다.

### Runtime Structure Notes

- 오케스트레이션 수동 실행과 예약 실행은 모두 기존 `run_batch()` 흐름을 유지한다.
- `run_batch()`에 선택적 `crawl_result_log_name` 인자를 추가해, 호출자가 명시한 경우에만 기존 `crawl_results.jsonl`에 기록한다.
- 설정 페이지 직접 실행의 기존 `crawler_name="configurable"` 흐름은 변경하지 않았다.
- 실패가 발생하면 UI 표시에서는 실패가 우선한다.

## Implementation Summary

- `crawler_app/orchestration.py`
  - `JobRunResult`를 `CrawlResult`로 변환해 기존 `log_result(APP_ROOT / "logs", ...)`에 넘기는 `_log_job_to_crawl_results()`를 추가했다.
  - `run_batch()`에 `crawl_result_log_name` 옵션을 추가했다.
  - job이 성공, 실패, 중복 중단, 주기 미도래, 이미 실행 중 스킵 상태가 되더라도 요청된 경우 동일한 JSONL 경로로 기록되게 했다.

- `crawler_app/web.py`
  - 오케스트레이션 페이지 수동 실행에서 `crawl_result_log_name="orchestration_manual"`을 전달한다.
  - `duplicate_stopped`/`duplicated_stopped` 표시값을 `성공` + `(duplicated_stopped)`로 변환하는 표시 helper를 추가했다.
  - 실패가 있으면 duplicate stop 보조 상태보다 `실패`를 우선 표시한다.

- `crawler_app/scheduled_runner.py`
  - Windows Scheduler 예약 실행에서 `crawl_result_log_name="orchestration_scheduled"`을 전달한다.

- `templates/orchestration.html`
  - 등록된 스케줄 영역, 저장된 모니터링 설정, 방금 실행한 결과, 실행 이력에서 표시용 상태값과 보조 사유를 출력하도록 변경했다.

## Validation

```powershell
.\.venv\Scripts\python.exe -m compileall main.py crawler_app crawlers
```

결과: 통과

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_web tests.test_orchestration tests.test_scheduled_runner tests.test_runtime_maintenance
```

결과: 66개 테스트 통과

```powershell
git diff --check
```

결과: 통과

## Remaining Risks

- 이번 push에서는 테스트 파일 변경을 commit하지 않는다. 따라서 해당 테스트 보강은 로컬 검증 근거로만 남고 원격에는 포함되지 않는다.
- 예약 실행의 OS-level `LastTaskResult`와 앱 내부 상태는 여전히 다른 출처의 값이다. UI는 앱 상태를 성공/실패 중심으로 보여주지만, Windows Task Scheduler 자체 결과 해석은 별도 확인이 필요할 수 있다.
- `logs/crawl_results.jsonl`은 누적 로그이므로 장기 운영 시 기존 runtime maintenance 정책에 따라 줄 수 제한/정리 정책을 계속 확인해야 한다.

## Remote

```text
hgz    https://github.com/hgz-902/test_crawl.git (fetch)
hgz    https://github.com/hgz-902/test_crawl.git (push)
origin https://github.com/K-Ternag/crawlService.git (fetch)
origin https://github.com/K-Ternag/crawlService.git (push)
```

## Push Command

```powershell
git push origin codex/advancement-latest-dedupe-20260528
```

## Push Result

Pending at record creation time.
