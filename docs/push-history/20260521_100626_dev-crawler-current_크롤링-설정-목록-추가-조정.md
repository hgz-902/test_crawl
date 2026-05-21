# Git Push Change Log - 크롤링 설정 목록 추가 조정

- Date: 2026-05-21 10:06:26 +09:00
- Repository: C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp
- Branch: dev/crawler-current
- Remote target: origin/dev/crawler-current
- Commit message: 크롤링 설정 목록 추가 조정
- Approved push target: https://github.com/K-Ternag/crawlService.git / dev/crawler-current

## Request

크롤링 설정 목록에서 직접 조정된 설정 파일들을 커밋/푸시한다. 이번 변경은 특정 개발 프롬프트에 따라 소스코드를 새로 수정한 작업이 아니므로, 별도 prompt 원문 기록은 추가하지 않는다.

## Changed Files

```text
configs/다음.json
configs/마켓인사이트.json
configs/산업부_보도자료.json
configs/시그널.json
configs/에프앤가이드.json
configs/인베스트조선.json
docs/push-history/20260521_100626_dev-crawler-current_크롤링-설정-목록-추가-조정.md
```

## Why These Changes Were Made

크롤링 설정 목록에서 사용자가 직접 조정한 수집 대상/필터/URL/XPath/실행 속성 변경을 원격 브랜치에 반영하기 위해 커밋한다. 이번 변경은 공통 workflow나 사이트별 crawler 소스 확장이 아니라 기존 JSON config 기반 구조 안에서 실행 설정을 조정하는 작업이다.

## Design Notes And Tradeoffs

### Existing Code Changed Because

소스코드 변경은 없다. 기존 JSON config 기반 크롤러 운영 방식에 따라 config 파일만 조정했다.

### Idea Or Constraint Behind The Change

- 시그널/마켓인사이트/인베스트조선은 최신 목록 URL과 사람이 확인한 XPath에 더 가깝게 정리한다.
- 필터 목록은 현재 검증/운영 확인에 필요한 키워드 중심으로 조정한다.
- 에프앤가이드는 개발 보류 placeholder 성격을 유지하되 headless 값을 현재 실행 기준으로 맞춘다.
- 정부 보도자료 계열은 기존 설정 구조를 유지하고 `updated_at`만 현재 설정 저장 이력에 맞춘다.

### Advantages

- 크롤링 설정 UI에서 보이는 최신 설정과 Git 원격 설정이 일치한다.
- 별도 소스 수정 없이 config만으로 운영 상태를 맞춘다.
- 변경 config들이 `validate_workflow_config`를 통과했음을 확인했다.

### Disadvantages Or Costs

- 일부 필터/검색어가 좁은 검증 키워드 중심으로 바뀌었기 때문에, 대량 운영 키워드가 필요하면 별도 config 재조정이 필요하다.
- 인베스트조선은 `pn={search_term}` 형태이므로 검색어 목록이 비어 있으면 기본 1페이지 동작에 의존한다. 여러 페이지 수집이 필요하면 search_terms에 페이지 번호를 넣는 운영 방식이 필요하다.

### Alternatives Considered Or Deferred

- 소스코드로 사이트별 예외 처리 추가: 기존 구조 보존 원칙에 맞지 않아 하지 않았다.
- 테스트 파일 수정/추가: `$git-push-change-log` 규칙상 기본 push 대상에서 제외하므로 하지 않았다.
- prompt 원문 추가: 사용자가 프롬프트 기반 수정이 아니라고 했으므로 추가하지 않았다.

### Collection Or Runtime Structure Notes

- 다음은 Kakao/Daum parser 구조를 유지하고 timestamp만 갱신됐다.
- 마켓인사이트는 Free News page 기반 URL과 XPath로 조정됐다.
- 시그널은 deal page에 `page={search_term}` 파라미터가 포함된 URL과 일반화된 XPath로 조정됐다.
- 인베스트조선은 `catid=2&pn={search_term}` 목록 URL, 최신 목록 XPath, 제목/본문 XPath가 조정됐다.
- 에프앤가이드는 유료 구독 보류 placeholder 상태를 유지한다.

## Implementation Summary

- `configs/다음.json`
  - `updated_at` 갱신.
- `configs/마켓인사이트.json`
  - 시작 URL을 `freenews?page={search_term}`로 조정.
  - 필터 키워드와 open_detail XPath 조정.
- `configs/산업부_보도자료.json`
  - `updated_at` 갱신.
- `configs/시그널.json`
  - 시작 URL을 `deal?page={search_term}&sort=` 형태로 조정.
  - 필터 키워드와 open_detail XPath 조정.
- `configs/에프앤가이드.json`
  - headless 값을 true로 조정.
  - `updated_at` 갱신.
- `configs/인베스트조선.json`
  - 시작 URL을 `catid=2&pn={search_term}` 형태로 조정.
  - 필터, open_detail XPath, 제목/본문 XPath 조정.

## Cumulative Prompt / Request Flow

이번 push는 별도 개발 프롬프트 원문을 기반으로 한 소스 변경이 아니라, 크롤링 설정 목록에서 직접 조정된 config 변경을 저장소에 반영하는 요청이다. 따라서 신규 prompt 원문 파일은 추가하지 않았다.

## Validation

Config validation:

```powershell
.\.venv\Scripts\python.exe - <<'PY'
from crawler_app.workflow import validate_workflow_config, normalize_workflow_config
# changed config 6개 load/normalize/validate
PY
```

Result:

```text
OK configs/다음.json 다음
OK configs/마켓인사이트.json 마켓인사이트
OK configs/산업부_보도자료.json 산업부_보도자료
OK configs/시그널.json 시그널
OK configs/에프앤가이드.json 에프앤가이드
OK configs/인베스트조선.json 인베스트조선
```

Unit tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Result:

```text
Ran 181 tests in 2.179s
OK
```

## Remaining Risks

- 실제 사이트 HTML이 바뀌면 config XPath를 다시 조정해야 한다.
- 이번 검증은 config schema/워크플로우 설정 유효성 및 전체 unit test 중심이다. 각 사이트의 실제 live crawling full run은 별도 운영 검수 대상이다.
- 인베스트조선/시그널/마켓인사이트의 page 파라미터 기반 다페이지 운용은 search_terms 설정 방식과 함께 확인해야 한다.

## Files Intentionally Excluded

```text
tests/*.py
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
