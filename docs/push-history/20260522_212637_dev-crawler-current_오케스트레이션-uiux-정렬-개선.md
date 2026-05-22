# 오케스트레이션 UI/UX 정렬 개선

## Push Preparation Status
- prepared_at: 2026-05-22 21:26 KST
- branch: `dev/crawler-current`
- remote: `origin https://github.com/K-Ternag/crawlService`
- target_url: `https://github.com/K-Ternag/crawlService/tree/dev/crawler-current`
- push_executed: no

## Purpose
Improve the `/orchestration` page so operators can understand selected jobs,
safe settings save, one-time proof run, monitoring lifecycle actions, scheduler
state, and evidence history without changing backend scheduler behavior.

## Cumulative Prompt / Request Flow
The user asked for the orchestrator page UI/UX to be better aligned and easier
to understand. The bounded UI pass should:

- make the page feel organized, not just decorated
- keep the selected targets visible before action buttons
- separate settings save, manual run, and monitoring start/stop by action risk
- avoid live crawling, real email send, or real Windows Scheduler mutation during validation
- preserve existing backend routes and action values

Follow-up user review found:

- the 1/2/3 guidance cards looked like a live current-step indicator because only step 1 was blue, but the state never changed
- the `+N` selected-target summary should reveal hidden targets on hover/focus
- additional confusing labels should be cleaned up if found

## Non-Expert Prompt Version Without Local Path

```text
오케스트레이터 페이지 화면을 좀 더 보기 좋고 쓰기 편하게 고쳐줘.

보고 싶은 화면:
오케스트레이션 페이지

내가 원하는 방향:
- 화면이 전체적으로 잘 정렬되어 있으면 좋겠어.
- 버튼들이 어떤 기능인지 헷갈리지 않게 보여야 해.
- 지금 어떤 작업들이 선택되어 있는지 한눈에 보이면 좋겠어.
- 저장, 수동 실행, 모니터링 시작/종료가 서로 다른 동작이라는 게 잘 드러나야 해.

꼭 고쳤으면 하는 부분:
1. 위쪽에 1, 2, 3번으로 된 설명 박스가 있는데, 1번만 파랗게 되어 있어서 지금 1단계를 진행 중인 것처럼 보여.
   그런데 실제로 저장하거나 실행해도 1번만 계속 파랗게 남아 있어.
   단계에 따라 색이 바뀌는 기능이 아니라면, 1/2/3번 박스를 모두 같은 색으로 보여줘.

2. “현재 선택 대상”에 선택된 작업들이 보이는 건 좋았어.
   그런데 작업이 많으면 `+8`처럼 줄여서 보이는데, 그 안에 어떤 작업들이 있는지 알 수가 없어.
   마우스를 올리면 숨겨진 작업 이름들이 보이게 해줘.

3. 내가 못 본 부분도 있을 수 있어.
   화면을 직접 보고, 헷갈릴 만한 표현이나 정렬이 이상한 부분이 있으면 같이 고쳐줘.
   다만 기능 자체가 바뀌면 안 되고, 화면을 더 이해하기 쉽게 만드는 쪽으로만 해줘.

주의할 점:
- 실제 크롤링 실행은 하지 마.
- 실제 이메일 발송은 하지 마.
- 실제 Windows 스케줄러 생성/삭제도 하지 마.
- 버튼이 서버로 보내는 기능 이름이나 경로는 함부로 바꾸지 마.
- 지금 화면을 보기 좋게 정리하는 게 목적이야.

확인해줬으면 하는 것:
- 페이지가 PC 화면에서 잘 정렬되는지
- 모바일처럼 좁은 화면에서도 이상하게 가로로 튀어나오지 않는지
- 1/2/3번 박스가 더 이상 “현재 단계”처럼 오해되지 않는지
- `+숫자`로 숨겨진 선택 작업을 마우스로 확인할 수 있는지
- 저장/수동 실행/모니터링 시작/종료가 서로 다른 기능처럼 보이는지
```

## Changed Behavior
- Added an operator guidance flow and selected-target summary near the top of `/orchestration`.
- Grouped action buttons into safer settings save, one-time manual run, and monitoring management lanes.
- Made scheduler status refresh visible as loading, refreshed, or unavailable instead of silently swallowing lazy fetch failure.
- Contained wide tables inside internal horizontal scroll on small screens.
- Removed misleading active/current color from the 1/2/3 guidance cards.
- Added hover/focus disclosure for hidden selected jobs summarized as `+N`.
- Cleaned first-scan labels toward operator-facing Korean wording.

## Files Intended For This Push
- `.gitignore`
- `templates/orchestration.html`
- `static/styles.css`
- `static/app.js`
- `docs/push-history/20260522_212637_dev-crawler-current_오케스트레이션-uiux-정렬-개선.md`

## Files Intentionally Excluded From Staging
- `AGENT_ACTIVITY_LOG.md`
- `CRITICAL_REVIEW.md`
- `QA_TEST_RESULT.md`
- `RED_TEAM_REVIEW.md`
- `UX_DECISION_RULING.md`
- `UX_NEXT_SESSION_PROMPT.md`
- `UX_PAIN_POINT_LEDGER.md`
- `UX_PRODUCT_UNDERSTANDING_PACKET.md`
- `UX_SCENARIO_PACKET.md`
- `UX_SCREEN_CONTRACT.md`
- `UX_STRUCTURE_PROPOSAL.md`
- `UX_TASK_CONTRACT.md`
- `VALIDATION_EVIDENCE.md`
- `docs/operator-ux-change-rationale-20260522.md`
- `memory/`
- `RUN_CONTEXT_ROLLING_CHECKPOINT.md`
- `RUN_CONTEXT_ROLLING_CHECKPOINT.json`
- `qa-artifacts/`
- `tests/`

These are local session-continuity, QA evidence, or test-only artifacts. They
are useful for this local workspace but are not required for the product UI
push. The product repository already ignores tests and most local markdown
session records, so this push keeps only source/UI files, required ignore
configuration, and the required push-history record.

## Design Judgment
- Kept the existing two-tab structure to reduce regression risk.
- Kept all backend route/action contracts unchanged.
- Used native `title` and `aria-label` for the hidden selected-target chip in this bounded pass instead of building a custom popover.
- Preserved technical detail in tables where needed but moved first-scan labels toward operator language.

## Alternatives Considered
- Add a third `Runs` tab: deferred because it would broaden tests and route expectations.
- Track real active step for the 1/2/3 cards: rejected because the current page does not have reliable state transitions for that UI promise.
- Build a full custom selected-target popover: deferred; native hover/focus metadata solves the current issue with lower risk.
- Change backend context to provide richer scheduler status: rejected for this UI-only slice.

## Validation
- `python -m unittest tests.test_web`: PASS.
- `python -m compileall -q crawler_app crawlers tests`: PASS.
- Browser QA evidence:
  - `qa-artifacts/operator-ux-20260522/`
  - `qa-artifacts/operator-ux-20260522-followup/`
- Follow-up browser metrics confirmed:
  - no body horizontal overflow on desktop/mobile config and scheduler views
  - all 1/2/3 flow cards have matching styles
  - all number badges have matching styles
- Synthetic 8-selected-job render confirmed the `+2` chip has hidden target metadata.

## Known Existing Failures Not Caused By This Change
- `python -m unittest tests.test_windows_scheduler`
  - known Python 3.10 `locale.getencoding` patch issue.
- `python -m unittest tests.test_orchestration tests.test_scheduled_runner`
  - known duplicate snapshot record ordering expectation.

## Secret / Sensitive Data Check
- No `.env` files are intended for staging.
- No screenshots or local QA artifacts are intended for staging.
- Push scope should be rechecked with `git diff --cached` before commit.

## Remaining Risks
- Native tooltips are simple. If the owner wants richer hidden-target browsing,
  a later custom popover can be added.
- Scheduler/results tab is still information-dense by nature. A later slice can
  split run evidence into its own tab if owner review asks for it.
