# 2026-05-29 API latest recent URL index 보완

## 사용자 요청

응. 이제 아까 너가 말했던 1번 해결 방향으로 수정을 진행해보자.

## 해석한 수정 방향

직전 조사에서 확인한 문제는 API형 네이버/다음/구글이 `latest.json`의 검색어/필터별 최신 boundary만으로 중복 진단을 하면서, rollup 이후 live `workflow_records.json`이 비어 있을 때 과거에 수집된 URL 중 group 최신이 아닌 URL을 놓칠 수 있다는 점이다.

따라서 이번 수정은 다음 방향으로 진행한다.

- 네이버/다음/구글 API형에만 source-wide recent URL index를 `latest.json`에 추가한다.
- 기존 `latest.json.records`의 검색어/필터별 boundary 구조는 유지한다.
- 중복 진단 시 같은 검색어/필터 boundary와 pub_date 기반 중단 정책을 먼저 적용한다.
- 그 다음 API형 source-wide recent URL index에 같은 `final_url`이 있으면 과거 수집 중복으로 판단하여 현재 검색어 수집을 중단한다.
- 같은 실행 안에서 이미 본 URL은 기존처럼 skip만 한다.
- 일반 사이트형 crawler의 `latest.json`, workflow_records, final_url 정책은 변경하지 않는다.

