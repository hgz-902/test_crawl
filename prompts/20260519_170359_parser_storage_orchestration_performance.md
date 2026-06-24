너는 기존 크롤링 오케스트레이션 수정 결과물을 다시 점검하고, 아래 테스트에서 발견된 미반영/오동작 사항을 수정해야 한다.

작업 경로:
C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp

대상 프로젝트:
- 기존 JSON config 기반 크롤러
- 기존 configs/*.json, workflow_records.json, outputs, runtime, orchestration_state 구조를 최대한 활용할 것
- 일반 사이트별 크롤러를 새로 늘리는 작업은 피하되, 이번 요청에 한해 네이버/구글/다음 parser/API 관련 소스코드 변경은 허용한다.
- 변경은 가능한 한 parser/API 저장 방식, workflow 저장 방식, orchestration page 성능 개선에 한정할 것.

중요:
- 이번 사용자 프롬프트도 즉시 prompt 기록 파일에 저장하라.
- 기존 prompt 기록을 덮어쓰지 말고 반드시 누적 구조로 저장하라.
- 예:
  - `prompt.md`에 날짜/시간/작업 제목별 섹션을 append
  - 또는 `prompts/YYYYMMDD_HHMMSS_<topic>.md`처럼 개별 파일로 누적 저장
- Git Push Change Log 스킬을 이용해 push할 때, 어떤 프롬프트 내용에 의해 수정이 진행되었는지 push record에 반드시 정리하라.
- 이때 이번 프롬프트 전문도 포함하라.
- secret이 포함된 프롬프트는 `[REDACTED_SECRET]`로 마스킹하라.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 절대 prompt 기록, README, push record, 로그, 커밋에 넣지 마라.

먼저 해야 할 일:
1. 이번 프롬프트 전문을 누적형 prompt 기록에 저장하라.
2. 현재 구현 상태를 확인하라.
3. 수정 전 pre-edit gate를 아래 형식으로 보고하라.
4. 그 다음 구현하라.

pre-edit gate 형식:

- classification: non-trivial
- reason
- source-code change needed: yes
- source-code change scope
- files likely to change
- validation plan
- risks

먼저 확인할 파일:
- README.md
- prompt.md 또는 prompts/ 하위 prompt 기록 파일
- crawler_app/workflow.py
- crawler_app/orchestration.py
- crawler_app/web.py
- crawler_app/naver_news_api.py
- crawler_app/google_news_rss.py
- crawler_app/daum_news_api.py
- 네이버/구글/다음 parser 저장 함수가 있는 파일
- templates/orchestration.html
- static/*.css
- configs/네이버뉴스.json
- configs/구글.json
- configs/다음.json
- tests 하위 parser/workflow/orchestration/web 관련 테스트
- .gitignore

수정 요청 1. 다음 API 결과를 item별 파일로 분리 저장

현재 다음 API의 경우 하나의 JSON 파일로 결과를 저장하는 것으로 보인다.

원하는 동작:
- 네이버, 구글처럼 다음 API 결과도 item별로 분리 저장되어야 한다.
- 단일 JSON 파일 하나에 전체 결과를 몰아넣는 방식은 피하라.
- 각 item이 독립적으로 추적/중복판정/필터분리/메일매칭에 사용될 수 있어야 한다.
- 저장 경로와 파일명은 기존 네이버/구글 방식과 최대한 일관되게 맞춰라.
- 예:
  - `outputs/daum/filter/001_<검색어>/items/<item_key>.json`
  - 또는 기존 프로젝트가 쓰는 item별 저장 convention
- item별 파일에는 최소 다음 정보가 들어가야 한다.
  - title
  - link/detail_url/originallink에 해당하는 URL
  - description/body
  - published_at/pubDate가 있으면 포함
  - source/api metadata
  - search_term
  - item index
- workflow_records.json에는 item별 record가 정상적으로 남아야 한다.
- 중복판정 key가 item별 URL/title을 기준으로 잘 생성되어야 한다.

허용 범위:
- 이번 요청에 한해 `crawler_app/daum_news_api.py` 등 다음 parser/API 소스코드 변경을 허용한다.
- 단, 사이트별 크롤러를 새로 만들지는 말고 기존 parser 저장 구조를 개선하라.

수정 요청 2. 네이버/구글/다음 parser/API 저장 방식이 다른 항목처럼 동작하게 수정

현재 네이버, 구글, 다음은 여러 번 크롤링할 때 다른 항목들과 다르게 동작한다.

문제:
- 다른 항목들은 `filter` 내에 새로운 항목만 추가로 저장되는 구조에 가깝다.
- 그런데 네이버/구글/다음은 크롤링할 때마다 `YYYYMMDD_1`, `YYYYMMDD_2`처럼 날짜 suffix가 붙은 새 폴더 또는 파일이 계속 생긴다.
- 이 때문에 같은 날짜 반복 실행 시 불필요하게 결과가 분산되고, 중복/필터 결과가 보기 어려워진다.

원하는 동작:
- 네이버, 구글, 다음도 다른 항목과 같은 저장 방식으로 맞춰라.
- 같은 날짜/같은 검색어 기준으로 불필요하게 `YYYYMMDD_1`, `YYYYMMDD_2` 같은 새 경로를 계속 만들지 마라.
- 새로 수집된 item만 적절한 filter/nonfilter 경로 아래 추가 저장되게 하라.
- 이미 저장된 item은 중복판정에 의해 skip 또는 stop되어야 한다.
- 반복 실행 시에도 경로가 계속 증식하지 않아야 한다.
- 단, 파일명 충돌이 있을 경우에는 item key/hash/title 기반으로 안정적으로 dedupe하거나 overwrite-safe한 방식으로 처리하라.
- 기존 filter/nonfilter 분리 정책과 workflow_records.json 중복판정 정책을 깨지 말라.

검증해야 할 실제 구조 예:
- 1회 실행 후:
  - `outputs/naver_news/filter/...`
  - `outputs/google/filter/...`
  - `outputs/daum/filter/...`
- 2회 실행 후:
  - `YYYYMMDD_1`, `YYYYMMDD_2` 같은 새 날짜 suffix 폴더가 불필요하게 늘지 않아야 함
  - 새 item만 추가되거나, 중복이면 아무 새 item도 추가되지 않아야 함
  - workflow_records.json은 정상 유지되어야 함

수정 요청 3. 오케스트레이션 페이지 진입 속도 저하 원인 정확히 파악 및 개선

현재 오케스트레이션 페이지 진입이 너무 느리다는 의견이 계속 전달된다.

현상:
- UI 수정 전에는 바로 들어가졌다.
- 지금은 오케스트레이션 페이지 진입에 3초~5초 사이가 걸린다.
- 개발 팀은 어떤 실행도 하지 않고 git에서 내려받자마자 테스트했는데도 느리다고 한다.
- 따라서 `run_history.json`이나 실행 이력 파일을 많이 읽어서 느리다는 설명은 원인으로 보기 어렵다.

해야 할 일:
- 원인을 추측하지 말고 실제로 측정하라.
- fresh clone 또는 실행 이력이 거의 없는 상태에서도 `/orchestration` 첫 진입이 느린 이유를 찾아라.
- 가능한 원인 후보:
  - page render 시 configs 전체를 과도하게 읽음
  - Windows Task Scheduler 조회를 동기적으로 수행함
  - PowerShell/schtasks 호출이 페이지 GET 요청 경로에서 blocking됨
  - scheduler details 조회가 느림
  - template에서 너무 많은 파일/stat/history를 읽음
  - prompt/history/outputs를 불필요하게 scan함
  - CSS/JS 문제가 아니라 server-side route가 느림
- 반드시 route 내부 구간별 timing을 임시 또는 테스트 가능한 방식으로 측정하라.
  - settings load 시간
  - registered jobs scan 시간
  - scheduler context 조회 시간
  - history load 시간
  - template render 전까지의 시간
- 원인이 확인되면 수정하라.

성능 개선 기준:
- `/orchestration` GET은 기본적으로 빠르게 렌더링되어야 한다.
- Windows Task Scheduler 조회가 느리다면:
  - 페이지 진입 시 즉시 blocking 조회하지 말라.
  - scheduler status는 lazy load endpoint, refresh button, background cache, timeout 제한 중 하나로 분리하라.
  - scheduler 조회 실패/timeout은 페이지 전체 렌더를 막지 않아야 한다.
- fresh clone 기준 `/orchestration` 첫 응답 목표:
  - 가능하면 1초 미만
  - 최소한 기존 3~5초보다 명확히 개선
- 성능 측정 결과를 QA artifact 또는 문서에 남겨라.

주의:
- 단순히 “빠를 것이다”라고 하지 말고 실제 측정값을 남겨라.
- `run_history.json` 때문이라고 단정하지 말라.
- 개발팀이 실행 이력 없는 상태에서 느리다고 했으므로, scheduler 조회나 config scan 같은 cold path를 우선 의심하라.

검증 요구사항:

자동 테스트:
- 다음 API item별 저장 테스트
- 네이버/구글/다음 반복 실행 시 `YYYYMMDD_1`, `YYYYMMDD_2` 같은 불필요한 경로가 늘지 않는 테스트
- parser item별 record가 workflow_records.json에 남는 테스트
- parser item별 duplicate key가 title+url/originallink 기반으로 생성되는 테스트
- `/orchestration` GET이 scheduler 조회 실패/지연 때문에 전체 렌더를 막지 않는 테스트
- scheduler context를 lazy load 또는 timeout 처리했다면 해당 endpoint 테스트

실제 또는 준실제 테스트:
- 네이버/구글/다음 각각 2회 실행
- 2회 실행 후 filter/nonfilter 아래 경로가 불필요하게 증식하지 않는지 확인
- 다음 API 결과가 item별 파일로 저장되는지 확인
- `/orchestration` 페이지 진입 시간을 수정 전/후 또는 최소 수정 후 측정
- 가능하면 fresh-ish 상태에서 측정
- 브라우저에서 오케스트레이션 페이지 열림 속도 확인
- 실제 Gmail 발송은 사용자 명시 승인 없이는 하지 마라

최종 보고 형식:
1. 수정한 파일 목록
2. 다음 API item별 저장 방식 변경 내용
3. 네이버/구글/다음 반복 실행 경로 증식 문제 수정 내용
4. workflow_records.json 및 중복판정과의 연결 방식
5. 오케스트레이션 페이지 느림 원인 분석 결과
6. 성능 개선 방식과 측정값
7. 테스트 결과
8. 실제 outputs 확인 결과
9. 브라우저/UI 검수 결과
10. prompt 누적 저장 경로
11. git push 여부
12. push record 경로
13. 남은 리스크

주의:
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 절대 커밋하지 마라.
- push 전 staged diff에서 secret이 없는지 반드시 확인하라.
- `git add .` 사용 금지. 수정한 파일만 선택적으로 stage하라.
- main/master에 push하지 마라.
