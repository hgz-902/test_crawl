# 수정 요청: workflow_records.json rolling window 정책 명확화

작업 경로:
`C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`

## 요청 내용

`workflow_records.json`이 2만 줄을 넘을 때의 리스크를 줄이기 위해 아래 정책으로 동작해야 한다.

- 2만 줄이 넘으면 단순히 수집 자료 데이터를 추가하는 것에서, 추가 및 삭제(혹은 수정)하는 것으로 변경한다.
- 2만 줄이 넘은 뒤 다시 최신 데이터가 쌓일 때마다 맨 아래에 있던 수집 데이터를 최신 데이터 개수만큼 제거한다.

## 동작 계약

- `workflow_records.json`은 최신 수집 records가 위에 prepend되는 구조를 유지한다.
- 저장 결과가 20,000줄을 넘지 않도록 한다.
- 제한을 초과하면 하단의 오래된 records부터 제거한다.
- 일반적으로 새 records가 추가되면 그만큼 오래된 records가 밀려나는 rolling window처럼 동작해야 한다.
- record마다 JSON 줄 수가 다를 수 있으므로, 최종 기준은 실제 저장되는 JSON line count 20,000줄 이하로 둔다.
- `item_count`는 제한 후 남은 records 수로 갱신한다.
- 중복 판정 기준 자체는 변경하지 않는다.

## 검증 요청

- 기존 records가 제한에 가까운 상태에서 새 records가 prepend될 때, 새 records는 유지되고 맨 아래 오래된 records가 제거되는지 확인한다.
- line count 제한이 유지되는지 확인한다.
- `item_count`가 남은 records 수와 일치하는지 확인한다.
- 기존 workflow/orchestration 테스트를 재실행한다.

## 주의사항

- 사이트별 크롤러 소스코드는 수정하지 않는다.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 기록하지 않는다.
- `git add .`는 사용하지 않는다.
- main/master에 push하지 않는다.
