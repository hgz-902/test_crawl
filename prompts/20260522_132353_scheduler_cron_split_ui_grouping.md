# 수정 요청: Cron 특정 분 스케줄러 지원 및 등록 스케줄 표시 집계 보완

작업 경로:
`C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`

대상 프로젝트:
- 기존 JSON config 기반 크롤러
- 기존 오케스트레이션 / Windows Task Scheduler 연동 구조
- 사이트별 크롤러 소스코드는 수정하지 말 것
- 변경은 공통 scheduler / scheduled runner / orchestration UI / scheduler registry 계층에 한정할 것

## 수정 배경

오케스트레이션 페이지의 cron 주기 설정에서 `* * * * *`, `*/10 * * * *`처럼 매분 또는 N분마다 실행되는 스케줄은 잘 동작하지만, `1,6,11,16 * * * *`처럼 매 시간의 특정 분 여러 개를 지정하는 cron 표현식은 Windows Task Scheduler에서 기대대로 동작하지 않는다.

Windows Task Scheduler가 Linux crontab 전체 문법을 그대로 지원하지 않으므로, 안전하게 변환 가능한 방식으로 cron 표현식을 해석하고 등록해야 한다.

또한 특정 분 목록을 Windows 작업 여러 개로 분리하여 등록하더라도, 오케스트레이션 페이지의 `등록된 스케줄 영역`에서는 운영자가 보기 쉽게 크롤링 항목당 하나의 스케줄처럼 보여야 한다.

## 요구사항 1. Cron 특정 분 목록 지원

아래 cron 표현식이 동작하도록 보완한다.

- `* * * * *`
- `*/5 * * * *`
- `*/10 * * * *`
- `1,6 * * * *`
- `1,6,11,16 * * * *`
- `1,3,6,9,12,15,18 * * * *`

구현 기준:
- `* * * * *`, `*/5 * * * *`, `*/10 * * * *`처럼 기존 Windows Task Scheduler에서 단일 작업으로 잘 동작하던 표현식은 기존처럼 task 1개만 생성한다.
- 기존에 단일 task로 동작하던 cron이 불필요하게 여러 schtasks로 쪼개지면 안 된다.
- `1,6,11,16 * * * *`처럼 특정 분 목록을 가진 표현식은 분 개수만큼 task를 생성한다.
- 분 목록이 2개면 2개, 7개면 7개가 생성되어야 하며, 특정 예시 개수에 하드코딩하면 안 된다.
- split task의 실제 실행은 각 Windows Task Scheduler 작업이 담당한다.
- scheduled runner가 cron gate를 사용할 경우, 실행 시점의 cron match 여부를 안전하게 판단한다.
- 지원하지 않는 cron은 조용히 무시하지 말고 검증 단계에서 오류를 보여준다.

## 요구사항 2. 등록된 스케줄 UI는 항목당 하나로 표시

Windows Task Scheduler 내부에서는 split task가 여러 개로 등록되더라도, 오케스트레이션 페이지의 `등록된 스케줄 영역`에서는 크롤링 항목당 하나의 row만 표시한다.

구현 기준:
- scheduler registry의 task를 `job_id` 기준으로 집계한다.
- `1,6,11,16 * * * *`처럼 4개 task로 분리되어도 UI에는 해당 crawler/job row 1개만 표시한다.
- `다음 실행` 컬럼은 분리된 task들의 next run time 중 현재 시각 이후 가장 가까운 시간을 표시한다.
  - 예: 현재 11:15이고 cron이 `11,16 * * * *`이면 다음 실행은 11:16
  - 예: 현재 11:17이고 cron이 `11,16 * * * *`이면 다음 실행은 12:11
- 최근 실행 / Last Result / Action path는 split task 정보를 대표값 또는 요약값으로 표시한다.
- 상태가 섞여 있으면 운영자가 알 수 있게 요약 표시한다.

## 요구사항 3. Task 컬럼 표시 방식

Task 컬럼에서는 실제 Windows Task Scheduler 경로 기반 이름을 보여준다.

단, split task의 세부 suffix는 숨긴다.

예:
- 실제 Windows task:
  - `\CrawlerOrchestration\<namespace>\crawler_<hash>_m11`
  - `\CrawlerOrchestration\<namespace>\crawler_<hash>_m16`
- UI 표시:
  - `\CrawlerOrchestration\<namespace>\crawler_<hash>`

즉, 스케줄러 경로와 대표 task 이름은 보여주되, 세부 분리 이름만 제거한다.

## 요구사항 4. 삭제 동작

UI에서 집계된 스케줄 row를 삭제할 때는 대표 task 하나만 삭제하면 안 된다.

구현 기준:
- 삭제 요청에 `job_id`가 있으면 scheduler registry에서 같은 `job_id`의 split task를 모두 찾아 삭제한다.
- 삭제 후 settings의 해당 job은 비활성화하고 `next_run_at`을 비운다.
- 실제 Windows Task Scheduler와 registry/UI 상태가 어긋나지 않게 한다.
- 이미 삭제된 task가 있어도 가능한 범위에서 안전하게 처리한다.

## 요구사항 5. 반복 클릭 / 동시 요청 검토

모니터링 종료 버튼을 로딩 완료 전 매우 빠르게 반복 클릭하면 같은 task를 여러 종료 요청이 동시에 삭제하려는 race condition이 발생할 수 있다.

우선 원인을 파악하고, 필요 시 다음 보완 방향을 제안한다.

- 프론트엔드에서 submit 직후 모니터링 시작/종료 버튼 비활성화
- 백엔드에서 scheduler start/stop 요청 lock 적용
- `Stop-OrchestrationJobs.ps1`에서 이미 삭제된 task는 실패가 아니라 삭제 완료 또는 skipped로 취급

이번 수정 범위에 포함할지 여부는 사용자 확인 후 결정한다.

## 검증 요청

자동 테스트:
- `*/5 * * * *`는 task 1개만 생성되는지 확인
- `* * * * *`는 task 1개만 생성되는지 확인
- `*/10 * * * *`는 task 1개만 생성되는지 확인
- `1,6 * * * *`는 task 2개가 생성되는지 확인
- `1,6,11,16 * * * *`는 task 4개가 생성되는지 확인
- split task registry가 UI에서 `job_id` 기준 1개 row로 집계되는지 확인
- split task들의 next run 중 가장 가까운 시간이 대표값으로 표시되는지 확인
- 집계 row 삭제 시 같은 `job_id`의 split task 전체가 삭제되는지 확인

실제 또는 준실제 테스트:
- 오케스트레이션 페이지에서 3개 항목을 선택하고 `*/5 * * * *`로 저장 후 모니터링 시작
- Windows Task Scheduler 또는 registry에서 항목당 task 1개만 생성되는지 확인
- `1,6,11,16 * * * *` 설정 시 해당 항목이 분리 task로 등록되는지 확인
- 분리 task가 있어도 UI에는 항목당 하나의 스케줄로 표시되는지 확인
- Task 컬럼이 `\CrawlerOrchestration\<namespace>\crawler_<hash>` 형태로 표시되고 `_m11`, `_m16` 등은 표시되지 않는지 확인
- 모니터링 종료 후 managed task가 정리되는지 확인

## 최종 보고에 포함할 내용

1. 수정한 파일 목록
2. cron 표현식별 Windows Task Scheduler 변환 방식
3. 단일 task 유지 대상과 split task 대상
4. 등록된 스케줄 UI 집계 방식
5. Task 컬럼 표시 방식
6. 삭제 동작에서 split task 전체를 처리하는 방식
7. 테스트 결과
8. 남은 리스크

## 주의사항

- 사이트별 크롤러 소스코드는 수정하지 않는다.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 기록하지 않는다.
- `git add .`는 사용하지 않는다.
- main/master에 push하지 않는다.
