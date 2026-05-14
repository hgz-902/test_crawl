---
name: playwright-config-runner
description: Use when the user wants to run, debug, or review the project's Playwright-based configurable crawler from a JSON file under configs/, especially when they want the execution result, errors, and config fixes explained.
---

# Playwright Config Runner

## Use This Skill

Use this skill when the task is:

- run a crawler from `configs/*.json`
- debug a failed Playwright crawl
- explain which JSON setting caused an error
- suggest concrete config fixes after a run

## Core Workflow

1. Identify the target config file under `configs/`.
2. Verify the file is valid JSON and uses `renderer: "playwright"`.
3. Run the crawler from the project root:

```bash
python main.py --crawler configurable --config "configs/사회공헌센터.json"
```

4. Inspect runtime output and logs:

- `logs/orchestrator.log`
- `logs/crawl_results.jsonl`

5. Report:

- whether the run succeeded
- which step failed
- the most likely cause
- the exact config keys to change

## What To Check In The Config

Focus on these keys first:

- `start_url`
- `base_url`
- `output_dir`
- `renderer`
- `steps`
- `search_terms`
- `list`
- `detail`
- `board_enabled`
- `board_list_xpath`
- `board_item_xpath`
- `board_item_tag`

## Failure Diagnosis

Classify failures in this order:

1. JSON parse error
2. missing required field
3. `renderer` mismatch
4. selector mismatch
5. timeout or wait-state issue
6. download failure
7. extraction failure

When a step fails, tie the error back to the nearest config field:

- `Page.goto` failure -> `start_url`, network access, or timeout
- selector not found -> `steps[].xpath`, `list`, or `detail`
- click/download mismatch -> `action`, `attr`, or `wait_state`
- empty extraction -> `detail` selector or wrong `attr`

## Required Output

When responding, keep the result concise and actionable:

- `설정 파일`
- `실행 결과`
- `오류 단계`
- `원인`
- `수정 제안`

If the run succeeded, include:

- downloaded files
- extracted files
- any remaining config improvements

If the run failed, include:

- the exact error text
- the step name
- the specific JSON key to change
- the smallest fix to try first

## Reporting Template

```text
설정 파일: configs/사회공헌센터.json
실행 결과: 실패
오류 단계: open_detail
원인: 현재 페이지 DOM과 XPath가 맞지 않음
수정 제안:
- board_list_xpath 재검토
- board_item_xpath를 실제 목록 구조에 맞게 변경
- 필요하면 wait_state를 visible로 변경
```

## Notes

- Prefer config fixes over code changes when the problem is expressible in JSON.
- If the problem is ambiguous, inspect the page structure before changing the config.
- Keep the answer focused on what should be changed, not on generic Playwright theory.
