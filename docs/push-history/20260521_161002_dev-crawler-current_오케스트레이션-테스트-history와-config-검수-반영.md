# 오케스트레이션 테스트 history와 config 검수 반영

- 일시: 2026-05-21 16:10:02 KST
- 저장소: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- 브랜치: `dev/crawler-current`
- 원격: `origin https://github.com/K-Ternag/crawlService.git`
- 커밋 메시지 예정: `오케스트레이션 테스트 history와 config 검수 반영`
- push 대상: `origin/dev/crawler-current`

## 요청 / 작업 단위

- 오케스트레이션 기능 테스트 결과를 push-history 아래 history 문서로 남긴다.
- 테스트 과정에서 변경한 크롤링 설정 JSON을 함께 반영한다.
- 제품 소스코드 변경 없이 config와 문서 중심으로 push한다.
- Codex 앱 전용 로컬 문서 경로는 git 공유 대상에서 제외되도록 ignore 기준을 유지한다.

## 변경 파일

- `.gitignore`
- `configs/구글.json`
- `configs/기후에너지부_보도자료.json`
- `configs/네이버뉴스.json`
- `configs/다음.json`
- `configs/마켓인사이트.json`
- `configs/시그널.json`
- `configs/연합뉴스.json`
- `docs/push-history/20260521_orchestration-test-history.md`
- `docs/push-history/20260521_161002_dev-crawler-current_오케스트레이션-테스트-history와-config-검수-반영.md`

## 변경 내용

- 오케스트레이션 기능 테스트 항목과 통과 결과를 `docs/push-history/20260521_orchestration-test-history.md`에 정리했다.
- 테스트 중 확인한 크롤링 설정 값을 config JSON에 반영했다.
  - Google / Naver / Daum API형 항목은 테스트 필터 조건을 반영했다.
  - Signal / YNA 등 일반 항목도 테스트 기준 filter 설정과 updated_at 변경을 반영했다.
  - MarketInsight / Climate Energy Ministry 항목은 테스트 후 저장된 updated_at 변경을 반영했다.
- Codex 앱 로컬 운영 문서인 `codex_app_agents.md`, `docs/codex-app/`가 git에 섞이지 않도록 `.gitignore`에 추가했다.

## 설계 판단

- 이번 변경은 크롤링 로직, 오케스트레이션 로직, 스케줄러 로직을 수정하지 않는다.
- 테스트 결과와 운영자가 확인한 config 상태만 공유하여, 개발 팀이 현재 검수 기준을 그대로 확인할 수 있게 한다.
- 테스트 history 문서를 push-history 아래에 두어 향후 push 시 변경 이력과 검수 기록을 함께 추적할 수 있게 한다.
- Codex 앱 전용 문서는 제품 산출물이 아니므로 계속 ignore한다.

## 보류한 대안

- 테스트 파일 변경 반영:
  - 현재 `$git-push-change-log` 규칙상 `tests/`는 기본적으로 stage하지 않는다.
  - 이번 요청도 소스코드 변경 없이 config와 history 중심 push이므로 제외한다.
- 오케스트레이션 로직 수정:
  - 이번 요청 범위가 테스트 보고와 config 반영이므로 제외한다.

## 검증

- `git diff --name-only -- '*.py' '*.html' '*.css' '*.js' '*.ts' '*.ps1' 'crawler_app/*' 'crawlers/*' 'scripts/*'`
  - 제품 소스코드 변경 없음.
  - dirty로 남은 것은 `tests/test_orchestration.py`, `tests/test_workflow.py`뿐이며 이번 commit에서 제외한다.
- JSON 설정 유효성 확인:
  - `configs/구글.json`: OK
  - `configs/기후에너지부_보도자료.json`: OK
  - `configs/네이버뉴스.json`: OK
  - `configs/다음.json`: OK
  - `configs/마켓인사이트.json`: OK
  - `configs/시그널.json`: OK
  - `configs/연합뉴스.json`: OK

## 의도적으로 제외한 파일

- `tests/test_orchestration.py`
- `tests/test_workflow.py`

위 파일은 로컬 검증용 dirty 상태로 남아 있으나, 이번 push는 테스트 보고 history와 크롤링 설정 반영이 목적이므로 stage하지 않는다.

## ignore 확인

`git status --short --ignored` 기준으로 다음 로컬 산출물/비밀/런타임 파일은 ignored 상태임을 확인했다.

- `.env`
- `.venv/`
- `codex_app_agents.md`
- `docs/codex-app/`
- `outputs/`
- `orchestration_state/`
- `runtime/`
- `logs/`
- `qa-artifacts/`
- `imsi/`
- `__pycache__/`

## 남은 리스크

- config 변경은 사용자가 테스트 중 저장한 운영 검수 기준을 반영한 것이므로, 이후 테스트 조건이 바뀌면 다시 config 저장이 필요할 수 있다.
- `tests/` 변경은 로컬에 남아 있으며 이번 push에는 포함되지 않는다.
