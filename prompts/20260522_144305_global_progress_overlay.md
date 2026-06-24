# 수정 요청: 모든 페이지 기능 실행 대기용 프로그레스바 추가

작업 경로:
`C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`

## 요청 내용

오케스트레이션 페이지, 크롤링 설정 페이지 등 모든 페이지에서 각 기능이 작동할 때 대기 시간 동안 화면을 덮는 프로그레스바가 생겨야 한다.

각 기능별로 진행 상황을 알 수 있는 방법이 있다면 확정적 인디케이터를 사용하고, 그게 아니라면 비확정적 인디케이터를 사용한다.

## 구현 기준

- 전체 페이지 공통 layout에 전역 progress overlay를 추가한다.
- form submit이 발생하면 화면을 덮는 overlay를 표시한다.
- 실제 percent 진행률을 알 수 없는 작업은 indeterminate progress bar로 표시한다.
- 현재 구조에서 크롤링 실행, 미리보기, 설정 저장, 삭제, 오케스트레이션 수동 실행, 모니터링 시작/종료 등은 요청 완료 전까지 서버 진행률을 알 수 없으므로 비확정 인디케이터를 사용한다.
- 기능별 메시지는 가능한 한 구분한다.
  - 설정 저장
  - 미리보기
  - 크롤링 실행
  - 삭제
  - 오케스트레이션 수동 실행
  - 모니터링 시작
  - 모니터링 종료
  - 스케줄러 삭제
- confirm 취소나 중복 submit 방어로 요청이 취소된 경우 overlay를 띄우지 않는다.
- 모니터링 시작/종료 버튼의 기존 중복 클릭 방어와 충돌하지 않아야 한다.
- 화면을 덮더라도 현재 UI 스타일을 유지하고, 운영 도구 화면처럼 과하지 않게 만든다.

## 검증 요청

- layout에 전역 progress overlay가 존재하는지 확인한다.
- CSS에 화면을 덮는 overlay와 indeterminate progress bar 스타일이 있는지 확인한다.
- JS가 form submit 시 overlay를 표시하는지 확인한다.
- confirm 취소 시 overlay가 뜨지 않는 흐름을 유지한다.
- config-form payload 생성과 충돌하지 않는지 확인한다.
- 모니터링 시작/종료 submit disable 처리와 충돌하지 않는지 확인한다.
- 기존 web/scheduler/workflow 테스트를 재실행한다.
- 가능하면 브라우저에서 오케스트레이션 또는 설정 실행 버튼 클릭 시 overlay가 보이는지 확인한다.

## 주의사항

- 사이트별 크롤러 소스코드는 수정하지 않는다.
- 실제 진행률 계산을 위해 백엔드 workflow 구조를 크게 바꾸지 않는다.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 기록하지 않는다.
- `git add .`는 사용하지 않는다.
- main/master에 push하지 않는다.
