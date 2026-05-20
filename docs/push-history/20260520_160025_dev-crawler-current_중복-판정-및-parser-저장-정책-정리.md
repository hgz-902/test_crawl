# Git Push Change Log - 중복 판정 및 parser 저장 정책 정리

- Date: 2026-05-20 16:00:25 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: dev/crawler-current
- Remote target: origin/dev/crawler-current
- Commit message: 중복 판정 및 parser 저장 정책 정리
- Approved push target: https://github.com/K-Ternag/crawlService.git / dev/crawler-current

## Request

workflow_records.json 기준 중복 판정이 실제 item 파일 생성 전에 적용되도록 보완하고, 네이버/다음/구글 parser 결과는 detail_url 기준, 일반 사이트는 final_url 기준으로 중복을 판단하도록 정리했다. Google은 같은 기사라도 서로 다른 detail_url로 들어오는 경우가 있어 detail_url 1차 판정 뒤 description 2차 판정을 추가했다.

## Changed Files

현재 커밋 포함 대상:

```text
crawler_app/duplicate_keys.py
crawler_app/orchestration.py
crawler_app/workflow.py
tests/test_orchestration.py
tests/test_workflow.py
prompts/20260520_141434_duplicate_key_rule_change.md
prompts/20260520_144226_duplicate_pre_save_collection.md
prompts/20260520_150031_google_description_second_pass.md
docs/push-history/20260520_160025_dev-crawler-current_중복-판정-및-parser-저장-정책-정리.md
```

의도적으로 제외한 dirty files:

```text
configs/구글.json
configs/네이버뉴스.json
configs/다음.json
configs/마켓인사이트.json
configs/시그널.json
configs/연합뉴스.json
configs/인베스트조선.json
```

위 config 변경은 테스트 중 검색어/limit가 임시로 줄어든 상태가 섞여 있다. 운영 키워드 목록을 덮을 위험이 있어 이번 소스 변경 커밋에는 포함하지 않는다.

## Why These Changes Were Made

기존 중복 판정은 title을 key에 포함하거나, workflow_records.json 저장 단계에서만 중복을 정리하는 성격이 남아 있었다. 그 결과 workflow_records.json에서는 중복이 사라져도 검색어별 items 폴더에는 동일 URL item JSON이 이름만 달라져 계속 쌓일 수 있었다.

사용자가 원하는 동작은 "이미 workflow_records.json에 기록된 URL이면 재수집 시 아예 item 파일을 만들지 않는 것"이다. 또한 한 검색어에서 이전 실행 중복을 만나면 그 검색어만 중단하고 다음 검색어는 계속 진행해야 하며, 같은 실행 안에서 앞 검색어와 겹친 item은 현재 검색어를 멈추지 않고 해당 item만 skip해야 한다.

## Design Notes And Tradeoffs

### Existing Code Changed Because

- 중복 key 생성 로직이 workflow/orchestration 사이에 나뉘어 있었고 title 기반 fallback이 남아 있었다.
- parser 저장 흐름은 item 파일을 만든 뒤 filter/nonfilter snapshot을 정리하는 방식이라, 저장 전 중복 차단 요구를 만족하지 못했다.
- Google News RSS는 detail_url만으로는 같은 기사 중복을 충분히 제거하지 못했다.

### Idea Or Constraint Behind The Change

- 중복 key 생성을 `crawler_app/duplicate_keys.py`로 분리해 direct workflow 실행과 orchestration 실행이 같은 기준을 쓰게 했다.
- 네이버/다음/구글은 parser/API 계열로 보고 `detail_url`만 1차 기준으로 사용한다.
- 일반 사이트는 기존 크롤링 산출 record의 `final_url`만 기준으로 사용한다.
- Google은 detail_url 다음에 description normalized key를 2차로 추가한다. 순서는 항상 detail_url -> description이다.

### Advantages

- 제목 기반 오탐/누락을 제거했다.
- 이미 수집된 parser item은 파일 생성 전에 차단된다.
- 같은 실행 중복과 이전 실행 중복의 정책이 분리되어 검색어 루프가 과하게 끊기지 않는다.
- orchestration 페이지 실행과 설정 목록 직접 실행이 같은 duplicate key 정책을 공유한다.

### Disadvantages Or Costs

- final_url/detail_url이 비어 있는 record는 중복 key를 만들 수 없어 신규로 취급된다.
- Google description 2차 판정은 본문 요약이 과도하게 같은 경우 중복으로 볼 수 있다. 다만 사용자가 요청한 Google 예외 정책에는 맞다.
- 기존 workflow_records.json 중 과거 필드가 불완전한 record는 새 기준으로는 중복 판정하지 못할 수 있다.

### Alternatives Considered Or Deferred

- 제목+URL 혼합 key 유지: 제목 변경/동일 제목 다른 기사 문제 때문에 제거했다.
- 모든 사이트에 description 2차 판정 적용: 일반 사이트에는 과한 오탐 가능성이 있어 Google만 예외 처리했다.
- 저장 후 cleanup만으로 처리: items 폴더에 중복 파일이 잠깐이라도 생기므로 요구사항과 맞지 않아 저장 전 차단으로 바꿨다.

### Collection Or Runtime Structure Notes

- parser direct run은 기존 output_dir 아래 `workflow_records.json`과 `parser_records.json`을 먼저 읽어 previous-run duplicate index를 만든다.
- previous-run duplicate는 `stop_scope=search_term`으로 현재 검색어만 멈춘다.
- same-run duplicate는 stop하지 않고 item만 skip한다.
- snapshot 저장은 기존 records와 새 records를 duplicate key 기준으로 merge한다.

## Implementation Summary

- `crawler_app/duplicate_keys.py` 추가
  - URL trim, fragment 제거, trailing slash 정리, query string 보존.
  - Naver/Daum/Google parser records는 `detail_url` 기준.
  - 일반 records는 `final_url` 기준.
  - Google은 `google_description:<normalized description>` 보조 key를 2차로 반환.
- `crawler_app/workflow.py`
  - parser item 저장 전에 기존 workflow snapshot 중복을 검사.
  - 이전 실행 중복은 현재 검색어만 stop.
  - 같은 실행 중복은 item만 skip.
  - 중복으로 저장 제외된 output files cleanup 대상 추적.
  - 기존 workflow_records.json snapshot을 보존/merge.
- `crawler_app/orchestration.py`
  - orchestration duplicate index와 same-run seen set도 shared duplicate keys를 사용.
  - Google description 2차 key가 orchestration 실행에도 동일 적용.
- `tests/test_orchestration.py`, `tests/test_workflow.py`
  - detail_url/final_url key 분리.
  - title 기반 key 제거.
  - filter/nonfilter snapshot 양쪽 duplicate index.
  - previous-run duplicate는 search term만 stop.
  - same-run duplicate는 skip only.
  - Google description 2차 중복 제거.
  - duplicate-first rerun 때 기존 snapshot 보존.

## Cumulative Prompt / Request Flow

### 2026-05-20 14:14 KST - 중복 제거 기준 변경

원문 prompt는 `prompts/20260520_141434_duplicate_key_rule_change.md`에 누적 저장했다. 핵심 요청은 네이버뉴스/다음/구글은 workflow_records.json의 detail_url만, 나머지 사이트는 final_url만 중복 기준으로 쓰고 title 기반 fallback을 제거하는 것이었다.

반영 결과: shared duplicate key module을 만들고 orchestration/workflow가 같은 기준을 사용하도록 수정했다.

### 2026-05-20 14:42 KST - 중복 자료 저장 전 차단 보완

원문 prompt는 `prompts/20260520_144226_duplicate_pre_save_collection.md`에 누적 저장했다. 핵심 요청은 workflow_records.json에서는 중복이 사라졌지만 items 파일은 이름만 달리 계속 쌓이는 문제를 막는 것이었다.

반영 결과: parser item 저장 전에 previous-run duplicate와 same-run duplicate를 분리 검사하도록 workflow를 수정했다. 이전 실행 중복은 현재 검색어만 중단하고, 같은 실행 중복은 item만 skip한다.

### 2026-05-20 15:00 KST - Google description 2차 중복 제거

원문 prompt는 `prompts/20260520_150031_google_description_second_pass.md`에 누적 저장했다. 핵심 요청은 Google에서 같은 기사인데 source/detail_url이 다르게 들어오는 경우 description으로 2차 중복 제거를 수행하는 것이었다.

반영 결과: Google duplicate keys는 detail_url을 1차로 반환하고 description normalized key를 2차로 반환한다. direct workflow와 orchestration batch 모두 같은 순서로 검사한다.

### 기록 제외된 운영성 요청

사용자가 명시적으로 저장하지 말라고 한 확인/운영 프롬프트와 실행 중인 수동 프로세스 중단 요청은 prompt 기록 및 push record의 원문 기록 대상에서 제외했다.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 181 tests in 2.030s
OK
```

추가로 이전 검증에서 다음 proof artifact를 확인했다.

```text
imsi\duplicate-key-pre-save-proof-20260520_1446\pre_save_duplicate_proof_summary.json
imsi\google-description-duplicate-proof-20260520_1506\google_description_duplicate_proof_summary.json
imsi\orchestration-dedup-parity-proof-20260520_1510\orchestration_dedup_parity_summary.json
```

이 proof들은 커밋 대상이 아닌 로컬 QA artifact라 stage하지 않는다.

## Remaining Risks

- 현재 dirty config files에는 테스트용 검색어/limit 변경이 남아 있다. 이번 커밋에는 포함하지 않았으므로, 운영 설정 확정 시 별도 검토가 필요하다.
- URL이 비어 있는 record는 안전하게 신규로 처리된다. 해당 사이트가 URL을 제공하지 않으면 중복 차단 효과가 제한된다.
- Google description 2차 판정은 RSS description 품질에 의존한다.

## Files Intentionally Excluded

```text
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
configs/*.json 테스트용 변경
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
