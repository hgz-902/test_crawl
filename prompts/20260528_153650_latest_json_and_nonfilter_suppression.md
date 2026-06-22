# Prompt: latest.json 추가 및 nonfilter 산출물 저장 중단

Date: 2026-05-28

## Original User Prompt

이제 다음 단계의 수정을 진행하자.
- workflow_records.json과 같은 depth에 latest를 관리하는 json 파일(latest.json)을 추가한다. latest에는 각 검색어별로 추후 중복 진단에 사용할 search_term, filter_term과 final_url만 남긴다. 예를 들어, outputs/naver_news/filter/latest.json이 생성된다면, 내부의 각 record에는 "search_term": "SK", "filter_term":"하이닉스", "final_url": "https://www.www.wwwww"와 같은 결과가 남아야 한다.
- latest.json에는 각 검색어별로 크롤링을 실행했을 때 검색어별 가장 최신 수집 자료의 record만 기록되어야 한다.
- 검색어나 필터링으로 걸러진 nonfilter의 경우에도, search_term에는 검색어, filter_term에는 nonfilter를 넣어 nonfilter에 수집된 자료 중 가장 최신 수집 자료의 record들을 반드시 기록해야 한다.
- 만약 검색어가 숫자로만 이루어진, 즉 페이지 파라미터로 쓰여 저장된다면, 그렇게 숫자로만 검색되어 수집된 모든 수집자료의 필터별 최신 수집 자료만 기록해야 한다. 즉, 검색어가 숫자로만 이루어져 있는지(ex: 010, 1, 10, 20, 0 등) 확인하는 정규식이 사용되어야 하며, filter_term이 다른 record를 구분하여 서로의 최신 record를 남겨야 한다. 단, 하나의 사이트에서 몇 개는 제대로된 검색어, 몇개는 페이지 파라미터로 저장된다면, 당연히 검색어는 검색어별로 최신 record가 따로 다시 기록되어야 한다.
- nonfilter 폴더는 제거하며, 거기에 저장되던 수집자료는 이제 수집하지 않는다. 오로지 그 중 최신 수집 자료만 latest.json에 search_term은 검색어, filter는 nonfilter, final_url은 수집자료의 최종 URL로 기록한다.
