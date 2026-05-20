# Git Push Change Log - 일반 사이트 중복 산출물 cleanup 보완

- Date: 2026-05-20 16:36:12 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: dev/crawler-current
- Remote target: origin/dev/crawler-current
- Commit message: 일반 사이트 중복 산출물 cleanup 보완
- Approved push target: https://github.com/K-Ternag/crawlService.git / dev/crawler-current

## Request

연합뉴스도 workflow_records.json에서는 중복 자료가 제거되는데 실제 수집 자료가 계속 쌓이는 문제를 확인하고 수정했다. 이어서 같은 일반 사이트 직접 실행 경로를 쓰는 시그널/마켓인사이트 등에도 동일 문제가 발생하지 않도록 공통 workflow 계층에서 처리했다. 또한 테스트 파일은 앞으로 `$git-push-change-log` 기본 push 대상에서 제외한다는 운영 규칙에 맞춰 새 테스트 파일 ignore 정책을 반영했다.

## Changed Files

현재 커밋 포함 대상:

```text
.gitignore
crawler_app/workflow.py
prompts/20260520_162456_yna_duplicate_output_cleanup.md
docs/push-history/20260520_163612_dev-crawler-current_일반-사이트-중복-산출물-cleanup-보완.md
```

의도적으로 제외한 dirty files:

```text
configs/구글.json
configs/기후에너지부_보도자료.json
configs/네이버뉴스.json
configs/다음.json
configs/마켓인사이트.json
configs/산업부_보도자료.json
configs/시그널.json
configs/연합뉴스.json
configs/인베스트조선.json
```

위 config 변경은 로컬 테스트용 검색어, loop_limit, headless 등 실행 설정 변경이 섞여 있다. 운영 설정을 덮을 수 있으므로 이번 소스 변경 커밋에서는 제외했다.

## Why These Changes Were Made

이전 수정은 parser/API 계열과 orchestration record policy에는 잘 적용됐지만, 일반 Playwright workflow를 설정 목록에서 직접 실행하는 경우 기존 workflow_records.json을 사전에 duplicate index로 읽지 않았다. 그 결과 최종 workflow_records.json merge 단계에서는 중복 record가 제외되지만, record 생성 과정에서 이미 만들어진 `texts/YYYYMMDD/...` 파일이 filter/nonfilter 밖 또는 root 검색어 폴더에 남을 수 있었다.

사용자가 확인한 연합뉴스 현상은 이 저장 순서 문제였다. 연합뉴스 전용 예외로 처리하면 시그널/마켓인사이트/인베스트조선 같은 일반 사이트 direct run에서 같은 문제가 반복될 수 있어 공통 workflow 계층에서 처리했다.

## Design Notes And Tradeoffs

### Existing Code Changed Because

- parser direct run에는 기존 workflow_records 기반 중복 index가 있었지만, 일반 Playwright direct run에는 같은 기본 정책이 없었다.
- `duplicate_stopped_without_new_records` 분기에서 조기 return하면서 cleanup이 실행되지 않았다.
- 테스트 파일 push 제외 방침을 `.gitignore`와 `$git-push-change-log` 운용 규칙에 맞춰야 했다.

### Idea Or Constraint Behind The Change

- 일반 direct workflow에서도 record_policy가 외부에서 주어지지 않으면 기본 duplicate policy를 생성한다.
- 기존 `workflow_records.json` / `parser_records.json`에서 duplicate key를 읽고, 일반 사이트는 `final_url` 기준으로 이전 실행 중복을 판단한다.
- 이전 실행 중복은 현재 검색어만 stop한다.
- 같은 실행 안에서 이미 본 중복은 item만 skip하고 검색어 수집은 계속한다.
- 중복으로 새 record가 하나도 남지 않는 경우에도 이번 실행에서 생성된 raw output file cleanup을 수행한다.

### Advantages

- 연합뉴스뿐 아니라 같은 일반 workflow 경로의 시그널/마켓인사이트/인베스트조선에도 동일한 예방 효과가 있다.
- workflow_records.json과 실제 `texts` 산출물의 중복 상태가 맞아진다.
- 테스트 파일을 새로 만들더라도 기본적으로 Git에 올라가지 않도록 막는다.

### Disadvantages Or Costs

- 일반 사이트에서 `final_url`이 비어 있으면 duplicate key를 만들 수 없어 신규로 처리된다.
- `.gitignore`의 `tests/`는 새 테스트 파일만 ignore한다. 이미 Git이 추적 중인 기존 tests 파일은 별도 untrack 승인 없이는 계속 tracked 상태다.

### Alternatives Considered Or Deferred

- 연합뉴스 config나 XPath 전용 예외: 같은 문제가 일반 사이트 전체에 반복될 수 있어 배제했다.
- 최종 snapshot 저장 뒤 cleanup만 수행: 이미 중복 여부를 알 수 있는 시점이 늦어져 불필요한 파일 생성/이동이 생길 수 있어 저장 전 policy를 추가했다.
- 기존 tracked tests 전체 untrack: 사용자에게 별도 명시 승인이 필요하므로 이번 커밋에서는 `.gitignore`만 반영했다.

### Collection Or Runtime Structure Notes

- Direct workflow 기본 duplicate policy는 output_dir 아래 `workflow_records.json`, `parser_records.json`을 검색해 index를 만든다.
- `filter/`와 `nonfilter/` 양쪽 snapshot을 모두 읽는다.
- `duplicate_stopped_without_new_records`일 때도 protected roots는 유지하고 root 임시 산출물만 삭제한다.

## Implementation Summary

- `crawler_app/workflow.py`
  - 일반 Playwright direct run에 기본 duplicate policy state 추가.
  - 이전 실행 중복은 `duplicate_stopped` + `stop_scope=search_term`.
  - 같은 실행 중복은 `same_run_duplicate_skipped`.
  - 중복 stop으로 새 record가 없을 때도 raw generated files cleanup 수행.
- `.gitignore`
  - 새 `tests/` 파일이 기본적으로 push 후보에 올라오지 않도록 ignore 추가.
- `prompts/20260520_162456_yna_duplicate_output_cleanup.md`
  - 이번 수정 요청 원문을 누적 prompt 기록으로 저장.

## Cumulative Prompt / Request Flow

### 2026-05-20 16:24 KST - 연합뉴스 중복 산출물 cleanup 보완

원문 prompt는 `prompts/20260520_162456_yna_duplicate_output_cleanup.md`에 저장했다. 요청은 연합뉴스에서 workflow_records.json에는 중복 자료가 제거되지만 실제 수집 자료가 계속 쌓이는 현상을 확인하고 수정하는 것이었다.

반영 결과: 연합뉴스 전용이 아니라 일반 Playwright workflow direct run 공통 경로에 기존 workflow_records 기반 duplicate policy와 duplicate-stopped cleanup을 적용했다.

### 2026-05-20 - 일반 사이트 적용 범위 확인

사용자가 시그널/마켓인사이트 같은 다른 일반 사이트에도 같은 문제가 발생하지 않게 된 것인지 확인했다. 공통 workflow 경로 수정이라 같은 final_url 기반 일반 사이트 direct run에도 적용된다고 답변했다.

### 2026-05-20 - 테스트 파일 push 제외 정책

이전 요청에서 `$git-push-change-log` 사용 시 테스트 파일을 push하지 않도록 요청했다. 스킬은 로컬에 수정했고, repo에는 새 테스트 파일 ignore를 위해 `.gitignore`에 `tests/`를 추가했다. 기존 tracked tests는 별도 승인 없이 untrack하지 않았다.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 181 tests in 1.923s
OK
```

준실제 연합뉴스 2회 실행 proof:

```text
imsi\yna_duplicate_output_cleanup_20260520_162833\summary.json
```

확인 결과:

```text
second_diagnostics.record_policy_stopped = true
second_diagnostics.record_policy_stop_reason = duplicate_stopped
second_diagnostics.record_policy_stop_metadata.stop_scope = search_term
new_files_on_second_run = []
```

즉, 2회차 중복 실행에서 workflow_records 기준 중복을 감지했고, 새 `texts` 산출물이 추가로 남지 않았다.

## Remaining Risks

- 기존 tracked `tests/*.py`는 여전히 저장소가 추적한다. 이번 방침은 새 테스트 파일 ignore 및 future push stage 제외이며, 기존 tests 제거는 별도 승인 후 `git rm --cached`가 필요하다.
- `final_url`이 비어 있는 일반 사이트 record는 중복 key를 만들 수 없어 신규로 처리된다.
- 로컬 dirty config files는 이번 커밋에서 제외되어 원격에는 반영되지 않는다.

## Files Intentionally Excluded

```text
configs/*.json 로컬 테스트 설정 변경
tests/*.py tracked test files
.env
.venv/
outputs/
orchestration_state/
runtime/
logs/
qa-artifacts/
imsi/
__pycache__/
.pytest_cache/
```

## Remote

```text
origin	https://github.com/K-Ternag/crawlService.git (fetch)
origin	https://github.com/K-Ternag/crawlService.git (push)
```

## Push Command

```powershell
git push origin dev/crawler-current
```

## Push Result

Pending at record creation time.
