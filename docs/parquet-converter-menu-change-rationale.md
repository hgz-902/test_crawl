# Parquet 전환 메뉴 변경 근거

## Change Rationale

- Changed area: UI 상단 메뉴, FastAPI route, parquet 다운로드 변환.
- Existing behavior: `outputs/*/tran/*.parquet` 파일은 서버 파일시스템에만 있고, 운영자가 브라우저에서 원본 파일로 직접 내려받을 방법이 없었다.
- Requested behavior: UI에서 parquet 목록을 보고, 전환 버튼을 누르면 parquet 내부 `content_bytes`를 원본 파일로 즉시 다운로드해야 한다.
- Why config/UI templates alone were not enough: parquet 내부 bytes를 읽어 HTTP 다운로드 응답으로 변환해야 하므로 서버 route가 필요했다.
- Source change made: `/parquet-converter`, `/parquet-converter/download`, `/parquet-converter/download-zip` route와 전용 화면을 추가했다.
- Tradeoff accepted: v1은 `outputs/*/tran/*.parquet`만 대상으로 하며, 서버에 복원 파일을 별도 저장하지 않고 요청 시 즉시 변환한다.
- Alternatives rejected: 복원 파일을 outputs에 재생성하는 방식은 산출물 오염과 삭제 정책 혼선을 만들 수 있어 제외했다.
- Validation evidence: `tests.test_web.ParquetConverterRouteTests`에서 목록, 단일 다운로드, ZIP 다운로드, 경로 차단을 검증한다.
- Remaining risk: 매우 큰 parquet을 다중 ZIP으로 묶을 때 메모리 사용량이 증가할 수 있다.
