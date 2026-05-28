# Workflow records schema and unique key

개발 팀과 논의 결과, workflow_records.json과 outpus의 구조부터 변경한 뒤 중복 정책 수정 등을 다시 진행하려 한다.
우선 workflow_records.json의 구조부터 변경하자.
- 각 records가 적히기 전에 적히는 search_terms와 filter_terms는 이제 해당 검색어 혹은 필터가 적용된 각 record 안에 적용된 검색어 또는 필터만 넣는다.
- 각 record에 있는 extracts의 내부 내용들은 이제 record_key와 같은 depth로 빼며, extracts는 제거한다.
- 각 record에는 동일한 depth에 record_key, search_term, filter_term, extract_title, description, pub_date, final_url만 존재해야 한다.
- Naver, Google, Daum 등에서 API로 수집할 때 생성되는 pubDate도 pub_date로 다시 명명하여 수집한다.
- search_term이나 filter_term이 비어있어도, record 안에 Value가 빈 칸으로라도 남아있어야 한다.
- API가 아닌 일반 언론사나 게시판에서 수집할 때, description이 수집되지 않지만 항목은 놔두고 빈 칸으로 놔둔다.
- API가 아닌 일반 언론사나 게시판에서 수집할 때, pub_date가 수집되지 않지만 수집 당시의 시분초까지 모두 기록해야 한다. 양식은 "Thu, 28 May 2026 13:54:00 +0900"과 같아야 한다.
- record_key는 유니크한 값을 생성해야 한다. crawler_id prefix + 짧은 fingerprint 형식을 사용하라. URL을 정규화한 뒤 수집일 YYYYMMDD와 합친 값을 Python blake2b 64비트로 변환하여 생성하라. 예시로 DAUM-72P4X8NQ5AAA과 같이 나온다.
- 이렇게 생성된 record_key는 관련 파일과 text 등의 이름에 모두 적용되어 있어야 한다. 예를 들어 기존에는 term001_item001_single_extract_title... 과 같았다면, 수정 후에는 {유니크하게생성된키}_single_extract_title... 과 같아져야 한다.
