# 2026-05-20 14:14:34 KST - 중복 제거 기준 변경

# 수정 요청: 중복 제거 기준 변경

현재 크롤링 수집 자료의 중복 판정이 제대로 동작하지 않는 것을 확인했습니다.

기존 중복 판정에서 제목(title)을 함께 사용하는 방식은 오탐/누락 가능성이 있으므로, 이제 제목은 중복 검색 조건에서 제거해주세요.

## 핵심 수정 요구사항

중복 제거 기준을 아래와 같이 변경해야 합니다.

## 중복 제거 기준

### 1. 네이버뉴스 / 다음 / 구글

아래 3개 항목은 `workflow_records.json`에 저장된 `detail_url` 값을 기준으로 중복을 판단해야 합니다.

- 네이버뉴스
- 다음
- 구글

즉, 새로 수집하려는 item의 `detail_url` 값이 기존 `workflow_records.json` 안의 `detail_url` 값과 같으면 중복으로 판단합니다.

### 2. 나머지 사이트

네이버뉴스 / 다음 / 구글을 제외한 나머지 모든 사이트는 `workflow_records.json`에 저장된 `final_url` 값을 기준으로 중복을 판단해야 합니다.

즉, 새로 수집하려는 item의 `final_url` 값이 기존 `workflow_records.json` 안의 `final_url` 값과 같으면 중복으로 판단합니다.

## 제거해야 할 기존 기준

아래 기준은 중복 판정에서 제거해주세요.

- `title`
- `title + final_url`
- `title + detail_url`
- 제목 기반 fallback 중복 판단

제목은 동일하지만 URL이 다른 경우가 있을 수 있고, 반대로 제목이 조금 달라져도 같은 자료일 수 있으므로 이번 요구사항에서는 제목을 중복 기준으로 사용하지 않습니다.

## 세부 동작 요구사항

- 기존 `workflow_records.json`을 읽어 중복 기준 index를 만들 때도 위 기준을 사용해야 합니다.
- 새로 수집되는 record와 비교할 때도 위 기준을 사용해야 합니다.
- 네이버뉴스 / 다음 / 구글은 반드시 `detail_url`만 비교 기준으로 사용해야 합니다.
- 나머지 사이트는 반드시 `final_url`만 비교 기준으로 사용해야 합니다.
- `detail_url` 또는 `final_url` 값이 비어 있는 경우에는 해당 record는 중복 판정 key를 만들 수 없으므로, 안전하게 신규 수집 대상으로 처리하되 warning/debug 로그를 남겨주세요.
- URL 비교 전에는 가능한 범위에서 URL 정규화를 적용해주세요.
  - 앞뒤 공백 제거
  - fragment 제거
  - 필요하면 trailing slash 정규화
  - 단, query string은 중복 판정에 중요한 값일 수 있으므로 임의로 제거하지 마세요.
- 중복 판정 로직은 사이트별 크롤러 코드에 흩뿌리지 말고, 공통 오케스트레이션/중복 판정 계층에서 처리해주세요.
- 네이버뉴스 / 다음 / 구글만 예외적으로 `detail_url` 기준을 쓰도록 분기하고, 나머지는 공통적으로 `final_url` 기준을 쓰는 구조로 작성해주세요.

## 기대 동작

예를 들어 네이버뉴스에서 새로 수집한 item의 `detail_url`이 기존 `outputs/naver_news/filter/workflow_records.json` 안에 이미 존재하면 중복으로 판단해야 합니다.

예를 들어 시그널에서 새로 수집한 item의 `final_url`이 기존 `outputs/signal/filter/workflow_records.json` 또는 `outputs/signal/nonfilter/workflow_records.json` 안에 이미 존재하면 중복으로 판단해야 합니다.

## 검증 요청

수정 후 아래 시나리오를 반드시 테스트해주세요.

1. 네이버뉴스를 1회 실행하여 `workflow_records.json`에 `detail_url`이 저장되는지 확인
2. 네이버뉴스를 다시 실행했을 때 기존 `detail_url`과 비교하여 중복이 탐지되는지 확인
3. 다음을 1회 실행하여 `workflow_records.json`에 `detail_url`이 저장되는지 확인
4. 다음을 다시 실행했을 때 기존 `detail_url`과 비교하여 중복이 탐지되는지 확인
5. 구글을 1회 실행하여 `workflow_records.json`에 `detail_url`이 저장되는지 확인
6. 구글을 다시 실행했을 때 기존 `detail_url`과 비교하여 중복이 탐지되는지 확인
7. 시그널 또는 다른 일반 사이트를 1회 실행하여 `workflow_records.json`에 `final_url`이 저장되는지 확인
8. 같은 일반 사이트를 다시 실행했을 때 기존 `final_url`과 비교하여 중복이 탐지되는지 확인
9. 제목이 같아도 URL이 다르면 중복으로 처리되지 않는지 확인
10. 제목이 달라도 기준 URL이 같으면 중복으로 처리되는지 확인
11. `filter`와 `nonfilter` 양쪽에 `workflow_records.json`이 있는 경우 두 파일 모두 중복 기준으로 읽는지 확인
12. 기존 테스트 전체를 실행하여 회귀가 없는지 확인

## 최종 보고에 포함할 내용

- 수정한 파일
- 기존 중복 판정 방식과 변경 후 방식 비교
- 네이버뉴스 / 다음 / 구글이 `detail_url` 기준으로 중복 판단되는 증거
- 나머지 사이트가 `final_url` 기준으로 중복 판단되는 증거
- 제목 기반 중복 판정이 제거되었는지 확인한 내용
- `filter` / `nonfilter`의 `workflow_records.json`을 모두 읽는지 확인한 내용
- 테스트 결과
- 남은 리스크
