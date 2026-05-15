# Task Classification

## Status
- task: crawler improvement baseline and local UI bring-up
- date: 2026-05-13
- classification: non-trivial
- workload level: Level 2 now, Level 3 for approved implementation slices

## Reason
- The overall requested roadmap touches external crawling, site-specific pacing, UI, scheduling, reporting, email delivery, and Git workflow.
- This first approved slice is limited to durable planning docs, local dependency setup, test/app startup verification, and making the UI/code visible to the user.
- No product feature implementation is included in this slice.

## Alpha Pre-Edit Gate
- classification: non-trivial
- reason: creating Alpha task artifacts and validating local runtime for a broader implementation program
- Alpha wave required: no for this docs/environment slice; yes for product feature implementation slices
- waiver: local-only setup waiver recorded in `RUN_CONTEXT.md`
- next action: create contract/plan/run context, install isolated dependencies, launch UI, open VS Code

## Scope Boundary
- In scope:
  - record proposed slices
  - create/update Alpha task docs
  - install dependencies into a local `.venv`
  - run existing tests
  - start the existing FastAPI UI
  - open the project in VS Code
- Out of scope:
  - changing crawler behavior
  - adding JOB orchestration code
  - adding scheduler/email features
  - editing site configs for production crawling

## 2026-05-14 Reclassification: Naver News Detail API Slice
- classification: non-trivial
- workload level: Level 3
- reason: this slice touches external API credentials, live API calls, pagination, detail URL fetching, JSON artifact generation, config behavior, and verification artifacts.
- Alpha wave required: yes
- waiver: none
- next action: implement through Alpha developer worker, then run reviewer/QA/auditor checks before final ruling.

## 2026-05-14 Reclassification: Naver API Editor UI And Body Cleanup Slice
- classification: non-trivial
- workload level: Level 2, promote to Level 3 if live crawling, secret handling, or retention/security findings expand.
- reason: this slice changes the user-facing editor UI, generated crawler config semantics, Naver API option validation, detail body cleanup, tests, and browser proof artifacts.
- Alpha wave required: yes
- waiver: none
- next action: Alpha developer worker implements the UI/body-cleanup slice; reviewer, QA, and auditor inspect before final ruling.

## 2026-05-14 Reclassification: Google News RSS Slice
- classification: non-trivial
- workload level: Level 2
- reason: this slice changes a provider config, Google RSS parser storage behavior, workflow output safety, external URL validation, live RSS proof, and regression tests.
- Alpha wave required: yes
- waiver: none
- next action: keep Google on `action=parser`, `attr=google`, verify `Chey Tae-won` and `SK` through Google News RSS, and stop before user-owned git push.

## 2026-05-14 Reclassification: TheBell Uniform HTML Slice (Superseded)
- classification: non-trivial
- workload level: Level 2
- reason: this slice first explored a provider parser, search-result pagination semantics, article-detail HTML extraction, editor UI scoping, config behavior, live proof, and regression tests; it was later superseded by the generic execution-step TheBell config.
- Alpha wave required: yes
- waiver: bounded main-implementation fallback permitted after the developer worker stalled; reviewer, QA, and auditor worker review remained required.
- next action: keep TheBell on generic execution steps, match Yonhap-style generic-news storage, and stop before user-owned git push.

## 2026-05-14 Reclassification: Source Change Guardrail
- classification: trivial
- workload level: Level 1
- reason: documentation-only guardrail to prevent unnecessary crawler source-code churn.
- Alpha wave required: no
- waiver: documentation-only.
- next action: require origin comparison, config/XPath-first evaluation, and `$git-push-change-log` notes before any future source-code change.

## 2026-05-15 Reclassification: Batch Job Orchestrator UI And Completion Email
- classification: non-trivial
- workload level: Level 3
- reason: this slice changes FastAPI routes/templates, in-process background scheduling, persistent job state, crawler execution safety, SMTP completion notification, and tests.
- Alpha wave required: yes
- waiver: none
- next action: Alpha developer worker implements the scheduler/job UI/email slice; reviewer, QA, and auditor inspect before final ruling.
