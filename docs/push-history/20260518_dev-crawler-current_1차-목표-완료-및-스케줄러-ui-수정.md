# 1차 목표 완료 및 스케줄러 UI 수정

## 기본 정보

- Date/time: 2026-05-18 16:07 KST
- Repository path: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- Branch: `dev/crawler-current`
- Remote target: `https://github.com/K-Ternag/crawlService/tree/dev/crawler-current`
- Commit message: `오케스트레이션 1차 목표 완료 및 스케줄러 UI 정리`

## 요청 / 작업 범위

크롤링+오케스트레이션 1차 목표가 완료된 상태를 최종 개발 브랜치로 올리기 위해, push 전에 남은 UI/스케줄러 표시 문제와 문서 정리를 반영했다.

이번 push에는 다음 흐름을 포함한다.

- 오케스트레이션 페이지의 등록된 스케줄러 표시 기준을 실제 scheduler registry 기준으로 정리
- 다른 로컬 환경에서 설정값만으로 등록된 스케줄러가 있는 것처럼 보이는 문제 방지
- 배치 대상 테이블에서 최근 실행 이력이 있는 항목과 없는 항목의 행 높이를 동일하게 보이도록 CSS 정리
- 산업부/기후에너지부 보도자료 config에 headless 실행 관련 특이사항 기록
- 기존 push-history 문서에서 최종 개발 브랜치와 무관한 임시 원격 업로드 표현 제거
- 원격 `dev/crawler-current`에 먼저 들어간 인베스트조선 설정 변경을 병합하고 보존

## 변경 파일

- `configs/기후에너지부_보도자료.json`
- `configs/산업부_보도자료.json`
- `crawler_app/web.py`
- `static/styles.css`
- `tests/test_web.py`
- `docs/push-history/20260518_dev-crawler-current_windows-task-scheduler-sync.md`
- `docs/push-history/20260518_dev-crawler-current_크롤링-오케스트레이션-프로그램-소스-이관.md`
- `docs/push-history/20260518_dev-crawler-current_1차-목표-완료-및-스케줄러-ui-수정.md`

## 변경 이유

### 스케줄러 표시 기준

다른 로컬 환경에서 실제 Windows Task Scheduler 작업을 등록한 적이 없는데도 오케스트레이션 페이지에 9개 스케줄러가 표시되는 문제가 확인됐다. 원인은 `scheduler_registry.json`이 비어 있을 때 `settings.json`의 enabled job 설정만 보고 스케줄러 row를 만들어 보여주는 fallback이었다.

운영자가 보는 "등록된 스케줄러"는 실제 스케줄러 동기화 기록이어야 하므로, enabled 설정만으로 등록된 것처럼 보여주는 동작을 제거했다.

### 배치 대상 테이블 행 높이

최근 실행 상태가 있는 항목은 보조 텍스트가 한 줄 더 생기고, 실행 시간이 긴 문자열로 표시되면서 행 높이가 달라졌다. 사용자는 배치 대상 목록을 운영 테이블처럼 빠르게 스캔해야 하므로, 같은 테이블 안에서는 행 높이를 고정하고 긴 값은 말줄임 처리하는 방향이 적합하다.

### 정부 사이트 headless 특이사항

산업부/기후에너지부 보도자료는 실제 테스트에서 headless 실행을 끄는 편이 안정적인 것으로 확인됐다. 소스코드 변경 없이 config notes와 headless 설정으로 운영자가 알아볼 수 있게 남겼다.

### 기록 문서 정리

최종 개발 브랜치로 push하는 흐름과 무관한 임시 원격 업로드 표현은 담당자가 변경 이력을 볼 때 혼동을 줄 수 있다. 이번 기록은 최종 개발 브랜치 기준의 구현/검증 내용만 남기도록 정리했다.

## 설계 판단과 tradeoff

- 스케줄러 UI는 실제 등록 기록인 scheduler registry만 읽는다.
  - 장점: 다른 PC의 로컬 설정 파일 때문에 가짜 스케줄러가 보이지 않는다.
  - 단점: Windows Task Scheduler를 앱 밖에서 직접 만든 경우 registry에 없으면 표시되지 않는다. 현재 운영 원칙은 앱 UI를 통한 생성/삭제이므로 이 tradeoff를 수용한다.
- 배치 대상 행 높이는 CSS에서 고정한다.
  - 장점: 최근 실행 이력 유무와 관계없이 테이블 스캔성이 좋아진다.
  - 단점: 아주 긴 값은 한 줄 말줄임으로 보이므로, 필요한 경우 상세 확인은 설정/상태 파일을 봐야 한다.
- 정부 사이트 안정성은 공통 크롤러 소스 변경이 아니라 config 특이사항으로 처리한다.
  - 장점: 개발팀이 선호하는 "소스 변경 최소화, 설정 중심 관리" 원칙을 지킨다.
  - 단점: 사이트별 런타임 특이사항은 config notes를 확인해야 한다.

## 구현 요약

- `crawler_app/web.py`
  - `_scheduler_context()`에서 enabled settings 기반 fallback 제거
  - 등록된 스케줄러 rows는 `load_scheduler_registry()` 결과만 사용
- `tests/test_web.py`
  - enabled job 설정이 있어도 registry가 없으면 등록된 스케줄러 row를 만들지 않는 회귀 테스트 추가
- `static/styles.css`
  - `.orchestration-table` tbody row/cell height를 고정
  - 배치 대상 테이블의 `.url` 값을 nowrap + ellipsis로 표시
- `configs/산업부_보도자료.json`, `configs/기후에너지부_보도자료.json`
  - headless 관련 운영 특이사항을 notes로 기록
  - 테스트 기준 loop limit 정리
- `docs/push-history/*`
  - 최종 개발 브랜치와 무관한 임시 원격 업로드 표현 제거
  - 이번 push 기록 추가

## 검증 결과

- `.\.venv\Scripts\python.exe -m unittest tests.test_web`
  - 결과: `Ran 19 tests ... OK`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
  - 결과: `Ran 137 tests ... OK`
- `git diff --check`
  - 결과: whitespace error 없음
  - 참고: Windows 작업 복사본의 LF -> CRLF 경고만 표시됨
- 문자열 점검
  - 최종 push 기록과 tracked 문서에서 임시 원격 URL 표현 제거 확인
- 비밀정보 점검
  - `.env`는 ignored 상태 유지
  - staged 대상에 SMTP password, Gmail 앱 비밀번호, API secret literal을 포함하지 않도록 확인 대상에 둔다.

## 의도적으로 제외한 파일

다음 파일/폴더는 로컬 실행 산출물, 하네스 세션 문서, 비밀정보, 캐시이므로 push 대상에서 제외한다.

- `.env`
- `.venv/`
- `outputs/`
- `orchestration_state/`
- `runtime/`
- `logs/`
- `qa-artifacts/`
- `crawler_app/__pycache__/`
- `crawlers/__pycache__/`
- `tests/__pycache__/`
- `DECISION_RULING.md`
- `RUN_CONTEXT.md`
- `TASK_CONTRACT.md`
- `TASK_PLAN.md`
- `TASK_CLASSIFICATION.md`
- `GUI_QA_PLAN.md`
- `GUI_QA_RESULT.md`
- `ORCHESTRATION_ALPHA_STATE.md`
- `THREAT_MODEL.md`
- `SECURITY_TEST_CHECKLIST.md`
- `SOURCE_CHANGE_GUARDRAIL.md`

## 누적 프롬프트 / 변경 흐름 추가 기록

- 사용자는 크롤링+오케스트레이션 프로그램의 1차 목표가 완료되었으므로 최종 개발 브랜치에 push하기를 요청했다.
- 사용자는 변경 기록에서 최종 개발 브랜치와 무관한 임시 원격 업로드 표현을 제거하라고 요청했다.
- 사용자는 다른 로컬 환경에서 스케줄러를 등록하지 않았는데도 9개가 표시되는 문제를 확인했다.
  - 조치: 등록된 스케줄러 UI는 실제 scheduler registry만 신뢰하도록 수정했다.
- 사용자는 배치 대상 테이블에서 최근 실행된 항목과 실행 이력이 없는 항목의 행 높이를 동일하게 맞추기를 요청했다.
  - 조치: 배치 대상 테이블 row/cell height를 고정하고 긴 값은 말줄임 처리했다.
- 사용자는 산업부 보도자료 headless 특이사항은 의도한 기록이므로 신경 쓰지 않아도 된다고 설명했다.
  - 조치: 해당 config 변경은 의도된 운영 특이사항으로 포함한다.
- 원격 개발 브랜치에 인베스트조선 config 변경이 먼저 들어가 있었다.
  - 조치: 해당 원격 변경을 병합해 보존하고, 현재 검수 기준의 `loop_limit=10`은 유지했다.

## 남은 리스크

- 앱 밖에서 Windows Task Scheduler 작업을 직접 수정하면 registry 표시와 실제 Windows 작업이 달라질 수 있다. 현재 운영은 앱 UI를 통한 생성/삭제를 전제로 한다.
- 배치 대상 테이블의 긴 값은 말줄임 처리되므로 모든 값을 한눈에 전부 보여주지는 않는다.
- 산업부/기후에너지부 보도자료의 headless 안정성은 사이트 상태와 브라우저 환경에 영향을 받을 수 있다.
- 실제 메일 발송은 `.env`/운영 환경변수와 UI의 발송 허용 설정에 따라 발생하므로, push 전후에도 비밀정보가 git에 들어가지 않았는지 확인해야 한다.

## Push Command

```powershell
git push -u origin dev/crawler-current:dev/crawler-current
```

## Push Result

TODO
