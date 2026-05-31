# 롤업 런타임 변경 프롬프트 기록 추가

- Created at: 2026-05-31 13:10:00
- Branch: dev/crawler-current
- Push target: https://github.com/hgz-902/test_crawl/tree/dev/crawler-current

## Purpose

직전 소스 변경 commit에 포함되지 않았던 개발 보완 프롬프트 기록을 `prompts/`에 추가한다.

## Why This Change Was Needed

소스코드를 변경한 작업에는 변경 요구사항을 재현할 수 있는 프롬프트 기록이 함께 남아야 한다. 직전 push에는 `docs/push-history` 기록은 포함되었지만, 별도 prompt artifact는 포함되지 않았다.

## What Changed

- `prompts/20260531_rollup_runtime_reload_scheduler_config_fixes.md` 추가.
- 프롬프트는 사용자 메시지 원문 복사가 아니라, 실제 지시와 운영 요구를 바탕으로 전문가가 개발 보완을 요청하는 형태로 재작성했다.
- 영어가 필요한 코드 식별자, 파일명, 명령어 외에는 한국어로 작성했다.

## Design Judgment

기존 prompt archive 관례를 따라 `prompts/`에 기능 단위 Markdown 파일을 추가했다. 직전 commit을 amend하지 않고 새 commit으로 남겨, 이미 push된 변경 이력을 보존한다.

## Alternatives Considered Or Deferred

- 직전 push-history 파일만 수정하는 방안은 prompt artifact 요구를 충족하지 못해 제외했다.
- 직전 commit amend 후 force-push하는 방안은 원격 이력 안정성을 해치므로 제외했다.

## Validation

- Markdown 문서 추가만 수행했다.
- `git diff --cached --name-only`로 prompt와 push-history만 staged되는지 확인한다.
- staged diff에서 secret성 문자열이 없는지 확인한다.

## Remaining Risks

- 이번 commit은 문서 기록 보완만 포함한다.
- 기존 unstaged test 파일 변경은 그대로 제외한다.

## Pre-Commit Checklist

- [x] Prompt artifact is included.
- [x] Push history is included.
- [x] No `.env`, output, runtime, qa artifact, or secret file is intentionally staged.
- [x] Existing unrelated dirty test files remain unstaged.
