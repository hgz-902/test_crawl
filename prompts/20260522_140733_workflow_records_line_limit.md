# 수정 요청: workflow_records.json 2만 줄 제한

작업 경로:
`C:\AI_JOB\firstproject\crawler_project\crawler-test-codexapp`

## 요청 내용

`workflow_records.json`은 이제 2만 줄로 제한해야 한다.

같은 크롤러가 반복적으로 수집하여 계속 쌓이게 놔두면 갈수록 용량이 늘어나고 파일 내용 추가/수정이 느려질 수 있기 때문이다.

## 구현 기준

- 대상 파일은 `outputs/<crawler>/filter/workflow_records.json`과 `outputs/<crawler>/nonfilter/workflow_records.json`이다.
- JSON 파일의 `records` 배열이 무제한 커지지 않도록 저장 직전에 제한한다.
- 기준은 실제 저장되는 JSON 직렬화 결과의 line count가 20,000줄을 넘지 않는 것이다.
- 최신 record가 위에 쌓이는 기존 prepend 정책은 유지한다.
- 제한을 초과하면 오래된 record부터 제거한다.
- `config_name`, `item_count`, `records` 등 기존 payload 구조는 유지한다.
- `item_count`는 제한 후 남은 record 수와 일치해야 한다.
- 중복 판정 기준 자체는 변경하지 않는다.
- 오래된 records가 잘리면 해당 오래된 자료는 이후 중복 판정 기준에서 제외될 수 있는데, 이는 파일 크기 제한을 위한 의도된 tradeoff로 기록한다.

## 검증 요청

- records가 많은 `workflow_records.json` 저장 시 20,000줄 이하로 trim되는지 확인한다.
- 최신 records가 앞쪽에 유지되고 오래된 records가 뒤에서 제거되는지 확인한다.
- `item_count`가 제한 후 records 수와 일치하는지 확인한다.
- filter와 nonfilter 모두 같은 저장 함수를 통해 제한되는지 확인한다.
- 기존 workflow/orchestration 테스트를 재실행한다.

## 주의사항

- 사이트별 크롤러 소스코드는 수정하지 않는다.
- 중복 제거 기준은 변경하지 않는다.
- `.env`, Gmail 앱 비밀번호, SMTP_PASSWORD, NAVER_CLIENT_SECRET, KAKAO_REST_API_KEY 등 secret은 기록하지 않는다.
- `git add .`는 사용하지 않는다.
- main/master에 push하지 않는다.
