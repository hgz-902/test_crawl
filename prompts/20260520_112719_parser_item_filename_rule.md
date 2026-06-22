# 2026-05-20 11:27:19 - Parser Item Filename Rule

## Original Prompt

# 수정 요청: 네이버/다음/구글 item JSON 파일명 규칙 변경

현재 네이버, 다음, 구글 크롤링 결과는 각 item별 JSON 파일로 분리 저장되고 있으나, 파일명이 사람이 구분하기 어려운 hash/code 형태로 생성되고 있습니다.

아래 요구사항에 맞게 파일명 생성 규칙을 변경해주세요.

## 대상

- 네이버뉴스
- 다음
- 구글

## 수정 요구사항

각 item별 JSON 파일명을 사람이 구분 가능한 형식으로 변경해야 합니다.

## 파일명 형식

```text
NAVER_YYYYMMDD_HHMISS_n.json
DAUM_YYYYMMDD_HHMISS_n.json
GOOGLE_YYYYMMDD_HHMISS_n.json
```

## 규칙

- `NAVER`, `DAUM`, `GOOGLE`은 수집 source를 의미합니다.
- `YYYYMMDD`는 해당 item이 저장되는 수집 시점의 연월일입니다.
- `HHMISS`는 해당 item이 저장되는 수집 시점의 시분초입니다.
- `n`은 같은 수집 시기에 저장되는 item의 순번입니다.
- 순번은 1부터 시작하고, 같은 수집 batch 안에서 저장 순서대로 `1, 2, 3, ...` 증가해야 합니다.

## 예시

```text
NAVER_20260520_143012_1.json
NAVER_20260520_143012_2.json
NAVER_20260520_143012_3.json

DAUM_20260520_143015_1.json
DAUM_20260520_143015_2.json

GOOGLE_20260520_143018_1.json
GOOGLE_20260520_143018_2.json
```

## 주의사항

- 네이버/다음/구글 외 다른 크롤러의 저장 방식은 변경하지 마세요.
- item별 JSON 분리 저장 구조는 유지하세요.
- 기존처럼 매 실행마다 불필요한 `YYYYMMDD_1`, `YYYYMMDD_2` 형태의 run suffix 폴더가 생기면 안 됩니다.
- `workflow_records.json`의 기록과 실제 item JSON 경로가 일치해야 합니다.
- 중복 제거 로직이 파일명 변경으로 깨지면 안 됩니다.
- 동일 batch 내 순번은 item 저장 순서 기준으로 안정적으로 부여되어야 합니다.
- 파일명에 기사 제목을 넣는 방식은 사용하지 마세요. 파일명 길이와 특수문자 문제가 생길 수 있습니다.

## 검증 요청

수정 후 아래를 반드시 테스트해주세요.

1. 네이버뉴스 수동 실행 후 item JSON 파일명이 `NAVER_YYYYMMDD_HHMISS_n.json` 형식인지 확인
2. 다음 수동 실행 후 item JSON 파일명이 `DAUM_YYYYMMDD_HHMISS_n.json` 형식인지 확인
3. 구글 수동 실행 후 item JSON 파일명이 `GOOGLE_YYYYMMDD_HHMISS_n.json` 형식인지 확인
4. 같은 실행 시점의 item들이 `_1`, `_2`, `_3` 순서로 저장되는지 확인
5. `workflow_records.json` 안의 output/file path가 변경된 실제 파일명과 일치하는지 확인
6. 반복 실행 시 기존 중복 판정이 계속 동작하는지 확인
7. 기존 테스트 전체를 실행하여 회귀가 없는지 확인

## 최종 보고에 포함할 내용

- 수정한 파일
- 파일명 생성 방식 설명
- 네이버/다음/구글 각각의 실제 생성 파일 예시
- `workflow_records.json` 경로 일치 여부
- 중복 판정 회귀 여부
- 테스트 결과
