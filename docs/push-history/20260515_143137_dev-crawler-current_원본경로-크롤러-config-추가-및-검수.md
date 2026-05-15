# 원본 경로 크롤러 config 추가 및 검수

- 일시: 2026-05-15 14:31:37 +09:00
- repository path: `C:\AI_JOB\firstproject\crawler_project\origin\crawlService-main`
- branch: `dev/crawler-current`
- remote target: `origin/dev/crawler-current`
- commit message: `원본 경로 기준 크롤러 설정 추가 및 검수`
- push command: `git push origin dev/crawler-current:dev/crawler-current`

## 요청 범위

원본 작업 폴더를 기준으로, 소스코드 변경 없이 설정과 XPath 중심으로 크롤러 대상 사이트를 추가하거나 검수한다. Naver, Daum 같은 API/parser 예외를 제외한 일반 사이트는 공통 실행 단계 구조 안에서 처리한다.

## 변경 파일

- `configs/더벨.json`
- `configs/에프앤가이드.json`
- `configs/마켓인사이트.json`
- `configs/시그널.json`
- `configs/연합뉴스.json`
- `configs/dart.json`
- `docs/push-history/20260515_143137_dev-crawler-current_원본경로-크롤러-config-추가-및-검수.md`

## 변경 이유

- 유료 구독 또는 회원 제한이 명확한 사이트는 실제 수집 로직을 억지로 추가하지 않고, 기본정보와 보류 사유만 남겨 운영자가 상태를 알 수 있게 했다.
- API/RSS가 아닌 일반 뉴스형 사이트는 소스코드를 늘리지 않고, 기존 실행 단계 구조에서 시작 URL, 검색어, XPath만으로 수집 가능성을 확인했다.
- 연합뉴스 최신뉴스는 검색어 기반 사이트가 아니라 페이지 번호 기반 최신 목록이므로, 소스코드 수정 없이 `search_terms`를 페이지 번호로 사용했다.
- DART는 일반 뉴스형 사이트와 다르게 AJAX 검색 결과를 반환하므로, 화면 폼을 조작하는 대신 AJAX 결과 endpoint를 시작 URL로 사용해 설정만으로 검수했다.

## 설계 판단과 tradeoff

- 더벨과 에프앤가이드는 유료 회원 가입이 필요한 대상으로 판단하여 placeholder 설정만 등록했다. 장점은 보류 사유가 UI에 남는 것이고, 단점은 실제 수집은 아직 수행하지 않는다는 점이다.
- 마켓인사이트와 시그널은 사람이 복사한 절대 XPath 형태를 우선하고, 필요한 경우에만 최소 일반화를 적용하는 방향으로 구성했다. 장점은 운영자가 개발자도구 XPath와 비교하기 쉽다는 점이고, 단점은 HTML 구조 변경에 대한 자동 적응성은 낮다는 점이다.
- 연합뉴스는 raw `li[n]` 구조가 광고/비기사 항목에서 끊길 수 있어 기사 항목 식별 속성인 `li[@data-cid][n]`를 사용했다. 장점은 페이지당 25개 기사 수집이 안정적이라는 점이고, 단점은 연합뉴스가 해당 속성을 바꾸면 XPath 재확인이 필요하다는 점이다.
- DART는 반복 step에서 `goto`를 쓸 수 없고, 직접 AJAX 결과 페이지에서는 팝업이 아니라 같은 탭 이동이 발생한다. 그래서 `click + same_tab`을 사용했다. 장점은 원본 workflow validation을 통과하면서 실제 상세 페이지로 이동한다는 점이고, 단점은 DART pagination은 아직 별도 검토가 필요하다는 점이다.

## 구현 요약

- `더벨`, `에프앤가이드`: 유료 회원 가입 필요에 따른 크롤링 보류 placeholder 설정 추가.
- `마켓인사이트`: `최태원`, `SK` 검색어 기준 뉴스 목록 상세 진입, 제목, 본문 추출 설정.
- `시그널`: `최태원`, `SK` 검색어 기준 뉴스 목록 상세 진입, 제목, 본문 추출 설정.
- `연합뉴스`: 최신뉴스 1~20페이지를 `search_terms` 페이지 번호 방식으로 순회하고, 페이지당 25개 기사 제목/본문을 추출하는 설정.
- `DART`: `SK`, `SK이노베이션` 회사명 검색 결과의 첫 페이지에서 검색어당 5개 공시 상세 제목/본문을 추출하는 설정.

## 검증 결과

- `.\.venv\Scripts\python.exe -m unittest tests.test_workflow`
  - 결과: 68 tests passed.
- 마켓인사이트 live 검수
  - 결과: `최태원`, `SK` 기준 6 records, 12 extracted files, 실패 0건.
- 시그널 live 검수
  - 결과: `최태원`, `SK` 기준 6 records, 12 extracted files, 실패 0건.
- 연합뉴스 live 검수
  - 결과: 1~20페이지, 총 500 records, 1000 extracted files, 실패 0건.
- DART live 검수
  - 결과: `SK` 5건, `SK이노베이션` 5건, 총 10 records, 20 extracted files, 실패 0건.
- 기후에너지부 보도자료 검수
  - 결과: 기존 설정으로 offset `0`, `200` 각각 성공. 이 검수는 설정 변경 없이 동작 확인만 수행했으므로 이번 commit 대상에서 제외한다.
- 산업통상부 보도자료 검수
  - 결과: 기존 숫자 `search_terms`는 페이지 번호 용도임을 확인. 검색어를 그대로 넣으면 `pageIndex=검색어`가 되어 오류가 발생하므로 이번 commit 대상에서 제외하고 리스크로만 남긴다.

## 남은 리스크

- DART는 다른 사이트와 구조가 달라 개발팀 판단이 필요하다. 현재 설정은 첫 번째 AJAX 검색 결과 페이지까지만 검수했다.
- 연합뉴스는 현재 20페이지 기준으로 구성되어 있어 최신뉴스 페이지 수가 바뀌면 `search_terms` 범위 조정이 필요하다.
- 더벨과 에프앤가이드는 실제 수집이 아니라 보류 상태 등록이다.
- 마켓인사이트, 시그널은 HTML 구조가 바뀌면 XPath 재확인이 필요하다.

## 의도적으로 제외한 파일

- `configs/산업부_보도자료.json`: 이번 작업은 테스트와 리스크 확인만 수행했고, 설정 변경을 commit하지 않는다.
- `configs/기후에너지부_보도자료.json`: 이번 작업은 기존 동작 검수만 수행했고, 설정 변경을 commit하지 않는다.
- `configs/인베스트조선.json`: 기존 항목 검수만 수행했고, 이번 commit에서 새 변경으로 다루지 않는다.
- 원격 기준에는 있으나 현재 원본 작업 폴더에는 없는 문서/기록 파일 삭제분: 이번 사이트 config 변경과 무관하므로 stage하지 않는다.
- `.env`, `.venv`, `outputs`, `logs`: 로컬 실행 산출물 또는 환경 파일이므로 stage하지 않는다.

## Push 전 확인

- 이번 commit은 소스코드 변경 없이 config와 push 기록만 포함한다.
- stage 대상은 위 변경 파일로 제한한다.
