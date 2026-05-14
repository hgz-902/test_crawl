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
