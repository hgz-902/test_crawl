# Source Change Guardrail

## Scope

This guardrail applies until the current crawler-site improvement program is complete.

The crawler team is sensitive to source-code churn, storage-path drift, UI workflow drift, and unclear reasons for code changes. Future site work must prefer existing product behavior and config-only changes unless there is a proven exception.

## Source Of Truth For Original Code

When comparing against original crawler behavior, always use:

`C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main`

Do not infer original behavior from memory or from the edited working tree when the origin copy can be checked.

## Baseline Site Types

- News-style execution-step sites:
  - Use the original Yonhap-style generic workflow as the baseline.
  - Prefer changing only `configs/*.json`, `start_url`, XPath, and existing execution-step values.
  - Expected output shape for generic news execution steps:
    - `<output_dir>\filter\<NNN_search_term>\texts\YYYYMMDD\...txt`
    - `<output_dir>\filter\workflow_records.json`
- Government or attachment-style sites:
  - Use `산업부_보도자료` as the baseline.
  - Add or keep `download_file` only when the target site actually provides files that must be downloaded.
- API-backed exceptions:
  - Naver and Daum are accepted exceptions because their collection path depends on APIs and environment credentials.
  - Additional API exceptions require an explicit reason and must keep credentials out of tracked config, UI, logs, and reports.
- RSS or platform-backed exceptions:
  - Use an existing parser path only when the platform/source format requires it, and record why the generic execution-step path is not enough.
  - Google News RSS is an existing origin exception, not a new arbitrary source-code pattern. The origin copy already uses `action=parser`, `attr=google`, and `crawler_app\google_news_rss.py`.
  - Do not convert Google RSS to generic XPath-only execution unless there is a separate approved source change to support RSS/XML parsing, structured item fields, and output compatibility through the generic path.

## Pre-Edit Source Change Gate

Before modifying shared source code, UI code, schema/storage behavior, or parser/provider code, record:

- target site and site type
- origin files checked under `C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main`
- closest baseline config checked, such as `연합뉴스` or `산업부_보도자료`
- whether config/XPath-only implementation was attempted or is sufficient
- exact reason source code must change
- expected blast radius across other configs
- output path or file-format impact
- UI/editor impact
- tests and live proof planned
- design notes for the later `git-push-change-log` record

If the reason is only convenience, cleanup, or style, do not change source code.

## Change Recording Rule

When any new code, source-code edit, storage-path change, UI/editor change, schema/config meaning change, or provider-specific exception is made, record the reason during development in the task docs.

The later push must use the `git-push-change-log` skill and include:

- why existing code or structure changed
- tradeoffs and disadvantages
- rejected alternatives
- site or collection constraint that forced the change
- validation evidence
- files intentionally excluded from staging

## Default Decision

Default to `config-only` for new crawler sites.

Default to `hold` or `rework` if a source-code change is proposed without origin comparison and a concrete reason.
