# 2026-05-21 10:57:37 workflow_records 기록 누적 순서 보완

# 수정 요청: workflow_records.json 기록 누적 순서 보완

이전에 전달한 프롬프트로 수정된 결과물을 테스트해봤다. 테스트 중 `workflow_records.json`에 쌓이는 수집 결과의 순서가 기대와 다르다는 점을 확인했다.

## 수정해야 할 사항

- `workflow_records.json`의 `records` 배열은 사용자가 보기에 최신 수집 자료가 가장 위에 오도록 저장되어야 한다.
- 다만 모든 crawler 항목에 신뢰 가능한 날짜 필드가 존재하는 것은 아니므로, 전체 항목에 대해 날짜 기반 재정렬을 강제하지 않는다.
- 기본 원칙은 **새로 수집된 record를 기존 records 앞쪽에 prepend**하는 방식이다.
- 즉, 새 크롤링 실행에서 수집된 자료는 기존 `workflow_records.json`의 기록보다 위에 쌓여야 한다.
- 기존 기록과 새 기록을 병합할 때:
  - 중복 제거 기준은 기존 로직을 유지한다.
  - 새로 수집된 non-duplicate record는 기존 records 앞에 위치해야 한다.
  - 기존 records의 상대 순서는 최대한 유지한다.
- parser/API 기반 항목인 네이버, 구글, 다음은 `pubDate` 등 신뢰 가능한 날짜 필드가 있으므로, 가능하다면 새로 수집된 records 내부에서는 최신순 정렬을 적용해도 된다.
- 하지만 일반 사이트 기반 항목은 날짜 필드가 없거나 불안정할 수 있으므로, 날짜 기준으로 억지 정렬하지 말고 수집 순서 기반으로 앞쪽에 누적한다.
- `filter/workflow_records.json`과 `nonfilter/workflow_records.json` 모두 같은 누적 원칙을 적용한다.
- 중복 때문에 현재 검색어가 중단되는 경우에도 기존 `workflow_records.json` 기록이 손상되거나 순서가 뒤섞이면 안 된다.

## 기대 동작 예시

기존 `workflow_records.json` 예시:

- old-1
- old-2

새 실행에서 새 자료 2건을 수집한 경우 기대 순서:

- new-1
- new-2
- old-1
- old-2

새 실행 중 `old-1`과 중복되는 자료가 발견된 경우 기대 순서:

- new-1
- old-1
- old-2

## 검증해야 할 사항

- 새로 수집된 non-duplicate record가 기존 기록보다 위에 저장되는지 확인한다.
- 기존 records의 상대 순서가 유지되는지 확인한다.
- 중복 제거 기준이 바뀌지 않았는지 확인한다.
- 중복 발견으로 현재 검색어가 중단되어도 새로 수집된 records와 기존 records가 정상 병합되는지 확인한다.
- 네이버, 구글, 다음은 가능하면 새 실행 내부에서 `pubDate` 기준 최신순이 유지되는지 확인한다.
- 일반 사이트는 날짜 필드가 없어도 수집 순서대로 새 기록이 앞쪽에 추가되는지 확인한다.
- `filter/workflow_records.json`과 `nonfilter/workflow_records.json` 모두 확인한다.
- 기존 테스트 전체를 실행한다.
- 가능하면 실제 UI 수동 실행으로 한 번 더 검증한다.

## 주의사항

- 중복 제거 기준은 변경하지 않는다.
- `workflow_records.json`의 기존 필드 구조를 불필요하게 크게 바꾸지 않는다.
- 모든 crawler에 날짜 필드가 있다고 가정하지 않는다.
- 날짜 기반 정렬은 네이버, 구글, 다음처럼 신뢰 가능한 날짜가 있는 경우에만 제한적으로 적용한다.
- secret, API key, SMTP 비밀번호 등을 로그나 문서에 출력하지 않는다.
- 수정 후 “새 record prepend 방식”과 “API형 항목 내부 최신순 처리 여부”를 설명한다.
