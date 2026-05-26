# hgz test_crawl 동기화 push 기록

- 일시: 2026-05-26 18:21 KST
- 저장소 경로: `C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`
- 로컬 브랜치: `dev/crawler-current`
- push 대상: `https://github.com/hgz-902/test_crawl.git`
- 원격 브랜치: `dev/crawler-current`
- commit message: `크롤링 설정 목록 갱신 및 hgz 테스트 저장소 동기화`

## 요청

현재 로컬 코드 기준으로 `hgz-902/test_crawl` 저장소에 push한다. 원격과 달라진 부분이 있어도 현재 로컬 기준으로 덮어써도 된다는 요청을 받았다.

## 변경 내용

이번 push는 최근 크롤링 설정 작업의 누적 결과를 hgz 테스트 저장소의 `dev/crawler-current` 브랜치에 반영하기 위한 것이다.

- 기존 crawler config 일부 갱신
  - `configs/theminjoo.json`
  - `configs/국무회의_브리핑.json`
  - `configs/국민의힘_보도자료.json`
  - `configs/국회의안정보시스템.json`
  - `configs/기후에너지부_보도자료.json`
  - `configs/산업부_보도자료.json`
  - `configs/시그널.json`
  - `configs/정책브리핑_보도자료.json`
- 신규 crawler config 추가
  - `configs/the_butter.json`
  - `configs/기후에너지부_공지사.json`
  - `configs/기후에너지부_설명자.json`
  - `configs/기후에너지부_입법예고.json`
  - `configs/기후에너지부_행정예고.json`
  - `configs/더나은미래.json`
  - `configs/리더뉴.json`
  - `configs/보건복지부_보도자료.json`
  - `configs/사회공헌센터_홍보미디어.json`
  - `configs/사회공헌플랫폼_배분사업.json`
  - `configs/산업부_공지사항.json`
  - `configs/산업부_보도설명자료.json`
  - `configs/산업부_입법예고.json`
  - `configs/산업부_행정예고.json`
  - `configs/에너지공단_공지사항.json`
  - `configs/의안정보시스템_법안발의.json`
  - `configs/전력거래소_공지사항.json`
  - `configs/한국사회가치평가.json`
  - `configs/한국석유관리원_공지사항.json`
  - `configs/한국에너지공단.json`
  - `configs/한국자동차환경협회_사업공고.json`
  - `configs/한국전력_홍보센터.json`
- push 기록 파일 추가
  - `docs/push-history/20260526_182106_dev-crawler-current_hgz-test-crawl-config-sync.md`

## 설계 판단

- 사이트별 설정값은 사람이 UI에서 조정할 수 있는 owner-controlled configuration이므로, 공통 crawler source code는 변경하지 않고 config 중심으로 반영한다.
- 이번 요청은 hgz 테스트 저장소 동기화가 목적이므로, 로컬 브랜치 이름과 같은 `dev/crawler-current` 원격 브랜치를 대상으로 한다.
- 사용자가 원격 덮어쓰기를 허용했지만, main/master가 아닌 작업 브랜치에 반영하여 운영 브랜치 오염 위험을 낮춘다.

## 제외 대상

아래 파일/폴더는 push 대상에서 제외한다.

- `.env`, `.env.*`: API key, SMTP password 등 secret 보관 파일
- `.venv/`, `__pycache__/`, `.pytest_cache/`: 로컬 실행 환경/캐시
- `outputs/`, `logs/`, `runtime/`, `orchestration_state/`, `qa-artifacts/`, `imsi/`: 실행 산출물 및 로컬 상태
- `tests/test_orchestration.py`, `tests/test_scheduled_runner.py`, `tests/test_web.py`, `tests/test_windows_scheduler.py`, `tests/test_workflow.py`: 현재 dirty 상태이나 기존 팀 규칙상 validation-only test 변경은 기본 push 대상에서 제외
- `attach/모니터링 사이트 및 키워드.xlsx`: 현재 dirty 상태이나 `.gitignore`의 `attach/` 정책상 로컬/첨부성 파일로 취급하여 이번 stage 대상에서 제외

## 검증

- `git status --short`, `git branch --show-current`, `git remote -v`, `git diff --stat` 확인
- hgz 저장소 원격 브랜치 확인: `git ls-remote --heads https://github.com/hgz-902/test_crawl.git`
- secret 문자열 스캔: config와 push-history 문서에서 실제 secret literal은 발견하지 않음. 환경변수 이름과 과거 push 기록의 보안 설명 문자열만 존재함.
- 이번 push 전 전체 자동 테스트는 실행하지 않음. 최근 작업은 config 중심이며, 일부 사이트 설정은 사용자가 직접 UI에서 검수 중이다.

## 남은 리스크

- 일부 신규 config는 사이트 구조와 XPath 상태에 따라 추가 조정이 필요할 수 있다.
- `tests/` 변경은 이번 commit에서 제외되어 hgz 테스트 저장소에는 반영되지 않는다.
- `attach/`의 xlsx 변경도 제외되어 원격에는 반영되지 않는다.
- force push는 원격 `dev/crawler-current` 브랜치의 이전 커밋을 로컬 기준으로 갱신한다.
