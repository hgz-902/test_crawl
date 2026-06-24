# API latest recent URL index 보완 및 hgz dev/crawler-current 덮어쓰기 push

- 작성 시각: 2026-05-29 19:15:59 KST
- 저장소 경로: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- 현재 로컬 브랜치: `codex/advancement-latest-dedupe-20260528`
- 원격 대상: `hgz/dev/crawler-current`
- 커밋 메시지: `API latest recent URL 중복 진단 보완`
- push 방식: 사용자가 hgz 쪽 예전 코드는 모두 갈아엎어도 된다고 승인했으므로 `--force-with-lease`로 현재 로컬 코드를 `hgz/dev/crawler-current`에 반영

## 요청 / 프롬프트 흐름

이번 변경은 API형 크롤러의 rollup 이후 중복 진단 누락을 보완하기 위한 작업이다.

관련 요청 흐름:

1. 네이버뉴스에서 같은 `record_key`와 같은 `final_url`이 `001_SK`와 `002_SK하이닉스` 아래에 중복 저장되는 현상이 확인되었다.
2. 원인 조사 결과, `latest.json`은 검색어/필터 그룹별 최신 boundary만 저장하므로, rollup 이후 live `workflow_records.json`이 비어 있으면 과거에 수집됐지만 해당 그룹의 최신 boundary가 아닌 URL을 놓칠 수 있음을 확인했다.
3. 사용자는 앞서 제안한 1번 해결 방향인 “API형 source-wide recent URL index 추가”를 적용하라고 요청했다.
4. 이어서 이번 변경사항을 `https://github.com/hgz-902/test_crawl/tree/dev/crawler-current`에 push하라고 요청했고, hgz 원격의 옛날 코드는 모두 갈아엎어도 된다고 승인했다.

원문 프롬프트 기록:

- `prompts/20260529_190856_api_latest_recent_url_index.md`

## 변경한 파일

- `README.md`
- `crawler_app/workflow.py`
- `prompts/20260529_190856_api_latest_recent_url_index.md`
- `docs/push-history/20260529_191559_hgz-dev-crawler-current_api-recent-url-index.md`

## 변경 이유

기존 `latest.json.records`는 검색어/필터별 “최신 경계” 역할을 한다. 이 구조는 검색어별 최신 기사보다 오래된 기사를 만나면 해당 검색어 수집을 중단시키는 데 유용하다.

하지만 API형 네이버/다음/구글은 여러 검색어에서 같은 기사 URL을 받을 수 있다. 예를 들어 `SK` 검색에서 이미 수집한 기사가 `SK하이닉스` 검색에서도 반환될 수 있다. 이때 `workflow_records.json`이 rollup되어 live 파일에서 사라지고, 해당 URL이 `latest.json.records`의 최신 boundary가 아니면, 과거 수집 URL임에도 다시 저장될 수 있었다.

따라서 API형에 한해 검색어/필터 boundary와 별개로 source-wide recent URL index가 필요했다.

## 구현 내용

### latest.json 확장

API형 네이버/다음/구글에 한해 `latest.json`에 `api_recent_records`를 추가했다.

- `records`: 기존처럼 검색어/필터별 최신 boundary 유지
- `api_recent_records`: API형 source 전체에서 최근 수집 URL index 유지

`api_recent_records`는 `search_term`, `filter_term`, `final_url`, `pub_date`를 저장한다. URL 기준으로 dedupe하며, 무한 증가를 막기 위해 현재 최대 2,000개까지만 유지한다.

### 중복 진단 순서

중복 진단은 다음 순서로 수행된다.

1. `latest.json.records`에서 현재 검색어/필터 또는 숫자형 페이지 파라미터 boundary를 먼저 확인한다.
2. 해당 boundary의 URL과 일치하거나, 현재 record의 `pub_date`가 boundary보다 오래되면 현재 검색어 수집을 중단한다.
3. boundary에 직접 포함되지 않은 URL이라도 API형 `api_recent_records`에 있으면 이전 실행에서 이미 수집된 URL로 보고 현재 검색어 수집을 중단한다.
4. 같은 실행 안에서 이미 본 URL은 이전 실행 중복이 아니므로 기존처럼 해당 item만 skip한다.

### 적용 범위

- 적용: Naver, Daum, Google API/parser형
- 미적용: 일반 사이트형 crawler
- 중복 기준: normalized `final_url`
- 제목 기반 중복 판정: 사용하지 않음

## 설계 판단

기존 `records`를 source-wide index로 바꾸지 않고 별도 `api_recent_records`를 추가했다. 이유는 검색어/필터별 latest boundary 정책은 여전히 필요하기 때문이다. `records`를 전체 URL index로 바꾸면 “검색어별 최신 경계를 만나면 현재 검색어를 중단”하는 정책이 흐려질 수 있다.

반대로 `api_recent_records`는 검색어 그룹 경계가 아니라 “이미 수집한 API URL을 다시 저장하지 않기 위한 보조 index”다. 그래서 같은 실행 안의 중복 skip과 이전 실행 중복 stop을 구분하는 기존 정책을 유지할 수 있다.

## 검증 결과

실행한 검증:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_workflow tests.test_orchestration
.\.venv\Scripts\python.exe -m compileall crawler_app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

결과:

- `tests.test_workflow tests.test_orchestration`: 122개 통과
- 전체 테스트: 217개 통과
- `compileall`: 통과

추가 준단위 검증:

- `latest.json.records`에는 `SK` 그룹의 최신 URL만 남는 상태를 만들었다.
- 같은 그룹의 더 오래된 URL은 `api_recent_records`에 남는지 확인했다.
- 이후 `SK하이닉스` 검색 후보 record가 동일 URL을 만나면 `latest_scope=api_recent_url`, `stop_scope=search_term`으로 `duplicate_boundary_stopped` 처리되는지 확인했다.

## 의도적으로 제외한 파일

다음 파일은 기존 로컬 검증용 dirty 상태이며 이번 push에 포함하지 않는다.

- `tests/test_orchestration.py`
- `tests/test_windows_scheduler.py`
- `tests/test_workflow.py`

다음 파일/폴더는 runtime, output, local artifact, secret 가능성이 있으므로 push하지 않는다.

- `.env`
- `.venv/`
- `outputs/`
- `runtime/`
- `logs/`
- `orchestration_state/`
- `qa-artifacts/`
- `imsi/`

## 남은 리스크

- `api_recent_records`는 무한 보존이 아니라 최근 2,000개 제한이다. 매우 장기간 rollup 후 같은 오래된 URL이 다시 API에서 반환되는 경우에는 별도 archive 기반 조회 index가 필요할 수 있다.
- hgz 원격 branch는 이번 push에서 현재 로컬 코드 기준으로 덮어쓴다. 사용자가 승인한 작업이지만, hgz branch에만 있던 별도 변경은 사라질 수 있다.

## Push 명령

```powershell
git push --force-with-lease hgz HEAD:dev/crawler-current
```
