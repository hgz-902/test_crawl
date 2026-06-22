# tran Flat Parquet Change Rationale

## Change Rationale

- Changed area: `filter` 산출물을 `tran` parquet으로 변환하는 저장 구조.
- Existing behavior: `filter` 하위 경로를 `tran` 아래에 그대로 복제하고 원본 파일명 뒤에 `.parquet`을 붙였다.
- Requested behavior: `tran` 바로 아래에 `download_YYYYMMDD_HHMISSffffff.parquet`, `text_YYYYMMDD_HHMISSffffff.parquet`, `metadata_YYYYMMDD_HHMISSffffff.parquet` 형식으로 평탄 저장한다.
- Why config/UI/templates/scripts were not enough: 변환 파일명과 저장 depth는 공통 workflow 변환 함수에서 결정되므로 config 변경만으로 바꿀 수 없다.
- Source change made: `crawler_app.workflow._export_filter_outputs_to_tran_parquet()`가 flat 파일명, rollup/latest 제외, metadata manifest를 생성하도록 변경했다.
- Tradeoff accepted: 원본 파일명을 parquet 파일명에서 제거하는 대신, `metadata_*.parquet`의 `tran_manifest_json`과 각 parquet row의 `source_relative_path`, `source_file_name`으로 매핑한다.
- Alternatives rejected: 다운로드 단계 sleep 추가는 내부 다운로드 loop가 순차 실행이므로 이번 문제의 본질이 아니어서 제외했다. 충돌은 변환 단계에서 `_001` suffix로 방어한다.
- Validation evidence: `tests/test_tran_parquet_export.py`에서 flat depth, timestamp naming, collision suffix, latest/rollup 제외, metadata manifest, schema를 검증한다.
- Remaining risk: 파일시스템 mtime 자체가 외부 복사나 수동 조작으로 바뀌면 파일명 timestamp도 바뀐다. 이 변경은 “수집 당시 시간 = 원본 파일 mtime”이라는 운영 전제를 따른다.
