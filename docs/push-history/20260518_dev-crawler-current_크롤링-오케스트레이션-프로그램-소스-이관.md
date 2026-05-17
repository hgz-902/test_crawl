# 크롤링 오케스트레이션 프로그램 소스 이관

## 목적

사용자 요청에 따라 현재 로컬 개발본의 크롤링 프로그램 소스코드, JSON 설정, 오케스트레이션 UI, 중복판정, 메일알림 관련 구현과 검증 문서를 `hgz-902/test_crawl` 저장소로 옮기기 위한 커밋 기록이다.

## 포함 범위

- 기존 JSON 설정 기반 크롤러 설정 파일(`configs/*.json`)
- 오케스트레이션 공통 계층(`crawler_app/orchestration.py`)
- 웹 UI 라우트와 템플릿, 스타일 변경
- 네이버/다음/구글/API/RSS/parser 흐름 관련 workflow 보강
- 네이버 News API `loop_limit` 기반 `display` 동적 반영
- 중복판정과 record policy 기반 중단 흐름
- 키워드 매칭 및 SMTP 메일 알림 흐름
- README, Alpha 상태/위협모델/보안 체크리스트/판정 기록
- 관련 단위 테스트

## 제외 범위

- `attach/`: Gmail 앱 비밀번호 등 로컬 비밀정보
- `outputs/`: 크롤링 결과물
- `runtime/`, `logs/`, `qa-artifacts/`, `orchestration_state/`: 로컬 실행/검증 산출물
- `imsi/`: 임시 테스트 백업과 메일 후보 캡처
- `configs copy/`: 로컬 중복 백업 설정 폴더

## 변경 이유

기존 프로젝트는 개별 JSON 설정 기반 실행은 가능했지만, 운영자가 여러 크롤러를 선택하고 주기, 중복판정, 키워드 알림을 함께 관리하는 공통 운영 계층이 부족했다. 이번 변경은 사이트별 크롤러 코드를 늘리는 방식이 아니라 기존 `configs/*.json`와 `workflow_records.json`를 재사용하는 오케스트레이션 계층을 추가하는 방향이다.

## 설계 판단

- DB 대신 JSON 상태 저장을 유지해 Windows Server 수동 운영과 추후 Task Scheduler 연동에 맞췄다.
- 중복판정은 각 config의 `output_dir` 아래 `workflow_records.json`를 재귀 탐색해 `filter`와 `nonfilter` 기록을 모두 읽는다.
- 중복 발견 시 현재 config 실행만 중단하고 다음 config는 계속 실행한다.
- SMTP 비밀번호와 API key는 코드와 설정에 저장하지 않고 환경변수/로컬 ignored 파일에서만 주입한다.
- 네이버 News API는 `display=100` 고정 요청 후 자르기에서, parser step의 `loop_limit`을 요청 `display`에 반영하는 방식으로 바꿨다.

## 보류한 대안

- Windows Task Scheduler 직접 등록: 시스템 부작용이 있어 UI 설정 저장과 수동 실행 중심으로 보류.
- DB 기반 job/record 저장: 현재 단계에서는 JSON 파일이 충분하고 운영 복잡도를 낮출 수 있어 보류.
- 전체 config 총량 제한: 현재 `loop_limit`은 검색어/실행 단위 제한이다. config 전체 총량 제한은 별도 요구가 있을 때 추가한다.

## 검증

- `python -m unittest tests.test_orchestration` 통과
- `python -m unittest tests.test_naver_news_api` 통과
- `python -m unittest tests.test_workflow` 통과
- `python -m unittest discover -s tests` 결과 115 tests OK
- 네이버 API 실제 소규모 호출에서 `loop_limit=20`이 `display=20`으로 반영됨을 확인
- 9개 항목 수동 배치 테스트에서 중복 발견 시 각 항목만 중단되고 다음 항목이 계속 실행됨을 확인
- 키워드 매칭 결과 기준 메일 재발송 성공 확인

## 비밀정보 점검

- 커밋 대상에서 `.env`, `attach/`, `outputs/`, `runtime/`, `orchestration_state/`, `imsi/` 제외
- 제공받은 API key, Naver secret, Gmail 앱 비밀번호 literal이 소스/문서/설정 커밋 대상에 없는지 스캔
- SMTP/API 환경변수명은 문서와 코드에 남지만 실제 비밀값은 포함하지 않는다.

## 남은 리스크

- GitHub push는 사용자 계정 인증 상태에 의존한다.
- 실제 SMTP 발송은 Gmail 앱 비밀번호 상태와 계정 보안 정책에 따라 실패할 수 있다.
- 일부 기존 문서와 설정 파일에는 이전 세션에서 남은 인코딩 흔적이 있을 수 있어, 별도 UTF-8 정리 작업이 필요할 수 있다.
- `loop_limit`은 현재 검색어/실행 단위 제한이며, config 전체 총량 제한은 별도 구현 대상이다.
