# 수정 요청: 모니터링 시작/종료 중복 요청 방어

작업 경로:
`C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`

## 발생한 오류

모니터링 종료 버튼을 로딩이 끝나기 전에 매우 빠르게 반복 클릭하면 아래와 같은 오류가 발생한다.

```text
모니터링 종료 중 일부 작업에서 오류가 발생했습니다: Unregister-ScheduledTask : CIM 서버 에서 Root/Microsoft/Windows/TaskScheduler/MSFT_ScheduledTask 클래스의 인스턴스에 대한 CIM 쿼리: SELECT * FROM MSFT_ScheduledTask WHERE ((TaskName LIKE 'crawler[_]3ba584394fbc')) AND ((TaskPath LIKE '\\CrawlerOrchestration\\9de182807988\\'))에서 일치하는 MSFT_ScheduledTask 개체를 찾지 못했습니다. 쿼리 매개 변수를 검증하고 다시 시도하십시오.
위치 C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp\scripts\Stop-OrchestrationJobs.ps1:55 문자:5
+ Unregister-ScheduledTask -TaskPath $task.TaskPath -TaskName $task ...
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
+ CategoryInfo : ObjectNotFound: (MSFT_ScheduledTask:String) [Unregister-ScheduledTask], CimJobException
+ FullyQualifiedErrorId : CmdletizationQuery_NotFound,Unregister-ScheduledTask
```

## 원인 가정

모니터링 종료 요청이 동시에 여러 개 들어오면 여러 PowerShell stop script가 같은 scheduled task 목록을 조회한 뒤 같은 task를 삭제하려고 한다. 먼저 실행된 요청이 task를 삭제하면, 뒤이어 실행된 요청은 이미 삭제된 task를 다시 `Unregister-ScheduledTask` 하면서 ObjectNotFound 오류를 낸다.

## 수정 요구사항

아래 3가지 방어를 모두 구현한다.

### 1. 프론트엔드 중복 클릭 방어

- 오케스트레이션 페이지에서 `모니터링 시작` 또는 `모니터링 종료` 버튼을 누르면 즉시 버튼을 disable 처리한다.
- 로딩 중 같은 버튼을 여러 번 빠르게 눌러도 같은 POST가 반복 전송되지 않게 한다.
- submit button을 disable해도 action 값이 서버에 전달되도록 hidden action 값을 안전하게 보존한다.

### 2. 백엔드 start/stop lock

- `모니터링 시작`과 `모니터링 종료` route에는 같은 프로세스 내 lock을 적용한다.
- start/sync 작업이 진행 중이면 다른 start/stop 요청은 동시에 실행되지 않아야 한다.
- stop 작업이 진행 중이면 다른 start/stop 요청은 동시에 실행되지 않아야 한다.
- 중복 요청은 실패 stacktrace 대신 사용자에게 이미 처리 중이라는 안내를 반환한다.

### 3. Stop-OrchestrationJobs.ps1 idempotent 처리

- `Stop-OrchestrationJobs.ps1`에서 이미 삭제된 scheduled task를 다시 삭제하려는 경우 오류로 중단하지 않는다.
- `Unregister-ScheduledTask`가 ObjectNotFound / NotFound 계열 오류를 반환하면 “이미 없음, 삭제 완료로 간주” 또는 skipped/deleted에 준하는 메시지로 처리한다.
- 이 경우에도 registry cleanup까지 계속 진행되어야 한다.
- 실제 오류는 기존처럼 실패로 보고한다.

## 검증 요청

자동 테스트:
- 모니터링 시작 중 lock이 잡혀 있으면 다른 시작 요청이 scheduler sync를 호출하지 않는지 확인한다.
- 모니터링 종료 중 lock이 잡혀 있으면 stop script를 다시 호출하지 않는지 확인한다.
- stop script가 이미 없는 task 오류를 idempotent하게 처리하는 구문을 포함하는지 확인한다.
- frontend JS가 orchestration start/stop submit 중복 방어를 포함하는지 확인한다.
- 기존 web/scheduler 테스트를 재실행한다.

실제 또는 준실제 테스트:
- 설정 저장 후 모니터링 시작
- 로딩 중 모니터링 시작/종료를 빠르게 여러 번 누르는 상황을 가정해 route 단에서 중복 방어가 되는지 확인
- 모니터링 종료 후 registry가 정리되고 UI가 오류 stacktrace를 표시하지 않는지 확인

## 주의사항

- 사이트별 크롤러 소스코드는 수정하지 않는다.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 기록하지 않는다.
- `git add .`는 사용하지 않는다.
- main/master에 push하지 않는다.
