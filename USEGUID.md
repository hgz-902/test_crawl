# Workflow Action Guide

이 문서는 `configurable` 워크플로우에서 `Action / Open / Attr / Wait`가 실제로 어떻게 동작하는지 정리한 사용 가이드입니다.

## 1. 네 가지 값의 역할

- `Action`: 요소에 대해 무엇을 할지 정합니다.
- `Open`: `click`일 때만 의미가 있습니다. 클릭 후 어떤 방식으로 열지 정합니다.
- `Attr`: 요소에서 어떤 값을 읽을지 정합니다.
- `Wait`: 요소가 어떤 상태가 될 때까지 기다릴지 정합니다.

## 2. Action 별 동작

### `click`

- 요소를 실제로 클릭합니다.
- `Open` 값에 따라 클릭 후 동작이 달라집니다.
- `Attr`는 사용하지 않습니다.

### `goto`

- 클릭하지 않습니다.
- `Attr`에서 읽은 값을 URL로 해석해서 바로 이동합니다.
- 보통 `href`가 있는 링크에서 사용합니다.

### `download`

- 요소에서 다운로드 경로를 찾거나, 클릭으로 다운로드를 유도합니다.
- `Attr`가 있으면 그 속성값으로 직접 다운로드 URL을 만들고,
- `Attr`가 없으면 `href`를 우선 사용하거나 클릭 기반 다운로드로 시도합니다.

### `extract`

- 요소의 텍스트, HTML, 또는 속성값을 읽어 저장합니다.
- `Attr` 값에 따라 읽는 대상이 달라집니다.

### `fill`

- 입력 필드에 값을 씁니다.
- 이때는 `Attr`를 사용하지 않습니다.

## 3. Open 별 동작

`Open`은 `click`에서만 의미가 있습니다.

### `auto`

- 요소가 `target="_blank"`면 새 탭/팝업으로 열기를 기다립니다.
- 그렇지 않으면 같은 탭에서 일반 클릭을 수행합니다.

### `same_tab`

- 같은 탭에서 클릭합니다.

### `popup`

- 새 탭/팝업이 열리는 것으로 가정하고 기다립니다.

## 4. Attr 별 의미

### `href`

- 링크 주소입니다.
- 일반 게시글 링크, 첨부파일 링크, 상세페이지 이동에 가장 많이 씁니다.

### `src`

- 이미지, 동영상, 파일 미리보기, 일부 첨부 리소스의 주소입니다.
- `href`가 없고 실제 리소스 주소가 `src`에 들어 있는 요소에서 씁니다.

### `text`

- 요소에 보이는 텍스트를 읽습니다.
- 제목, 본문, 설명 문구 추출에 씁니다.

### `html`

- 요소의 HTML 원문을 읽습니다.
- 구조 보존이 필요할 때 씁니다.

## 5. Wait 별 의미

### `attached`

- DOM에 붙을 때까지 기다립니다.
- 가장 일반적인 기본값입니다.

### `visible`

- 화면에 보여질 때까지 기다립니다.

### `hidden`

- 화면에서 숨겨질 때까지 기다립니다.

### `detached`

- DOM에서 제거될 때까지 기다립니다.

### `auto`

- 별도 지정이 없을 때의 기본 대기입니다.

## 6. 조합별 예제

### 예제 1. 상세페이지 링크를 클릭해서 새 탭으로 열기

- `Action = click`
- `Open = popup`
- `Wait = attached`

사용 시점:

- 목록의 제목 링크를 눌러 상세페이지로 들어갈 때
- 링크가 새 탭이나 팝업으로 열리는 사이트에서

동작:

- 요소를 클릭합니다.
- `target="_blank"` 또는 팝업 동작을 기다립니다.

예시:

- 목록의 제목 `<a href="...">`를 눌러 상세페이지를 여는 경우

### 예제 2. 클릭 대신 링크 주소로 바로 이동

- `Action = goto`
- `Attr = href`
- `Wait = attached`

사용 시점:

- 클릭 없이 링크 주소로 바로 들어가고 싶을 때
- 상세 URL이 `href`에 들어 있는 경우

동작:

- `href` 값을 읽어서 바로 이동합니다.

예시:

- 버튼처럼 보이지만 실제 목적지가 `href`에 들어 있는 링크

### 예제 3. 이미지 주소를 직접 열기

- `Action = goto`
- `Attr = src`
- `Wait = attached`

사용 시점:

- 이미지 요소나 미디어 요소의 실제 주소가 `src`에 있을 때
- 클릭 이벤트가 필요 없고 리소스 주소만 확보하면 될 때

동작:

- `src` 값을 읽어서 그 주소로 바로 이동합니다.

예시:

- 썸네일 이미지의 원본 주소를 열어야 하는 경우

### 예제 4. 직접 URL 이동

- `Action = goto`
- `Attr = href`
- `Wait = attached`

사용 시점:

- 요소 클릭이 필요 없고, 링크 주소로 바로 이동하면 될 때
- 가장 단순한 이동 방식이 필요할 때

동작:

- `href` 값을 읽어서 `page.goto()`로 이동합니다.

예시:

- 목록의 링크를 굳이 누르지 않고 바로 상세 URL로 들어가기

### 예제 5. 첨부파일 다운로드

- `Action = download`
- `Attr = href`
- `Wait = attached`

사용 시점:

- PDF, HWPX, ZIP 같은 첨부파일 링크가 있을 때

동작:

- `href`를 읽어서 직접 다운로드 요청을 보냅니다.
- 실패하면 클릭 기반 다운로드로 다시 시도할 수 있습니다.

예시:

- 보도자료 상세페이지의 `첨부파일 다운로드 링크`

### 예제 6. 본문 텍스트 추출

- `Action = extract`
- `Attr = text`
- `Wait = visible`

사용 시점:

- 제목, 본문, 요약 문구를 저장할 때

동작:

- 요소의 화면 텍스트를 읽습니다.

예시:

- 상세페이지 본문 영역의 텍스트 저장

### 예제 7. HTML 원문 추출

- `Action = extract`
- `Attr = html`
- `Wait = attached`

사용 시점:

- 나중에 구조를 보존한 채 후처리해야 할 때

동작:

- 요소 내부 HTML을 그대로 읽습니다.

예시:

- 본문 영역의 원문 HTML 저장

### 예제 8. 검색창 입력

- `Action = fill`
- `Wait = visible`
- `Attr = 사용 안 함`

사용 시점:

- 검색어 입력 후 목록 갱신이 필요한 경우

동작:

- 입력 필드에 값을 채웁니다.

예시:

- 검색창에 현재 검색어를 넣고 조회 버튼을 누르는 흐름

## 7. Action / Attr 한눈에 보기

- `click`: 눌러야 움직이면 사용
- `goto`: 주소가 바로 보이면 사용
- `download`: 파일을 바로 받거나 클릭 후 파일이 내려받아지면 사용
- `href`: `a` 태그 주소를 읽을 때 사용
- `src`: `img`, `iframe` 같은 리소스 주소를 읽을 때 사용
- `javascript:`가 보이면 무조건 `click`이 아니라, 파일 저장이면 `download`, 화면 동작이면 `click`

## 8. Action / Attr 초간단 판단표

### Action 은 뭐를 할지 고르는 것

| Action | 언제 쓰나 | 한 줄 설명 |
| --- | --- | --- |
| `click` | 눌러야 다음 동작이 생길 때 | 버튼처럼 "클릭"이 필요한 경우 |
| `goto` | 이미 URL이 들어 있을 때 | 주소로 바로 이동하는 경우 |
| `download` | 파일 URL이 바로 있을 때 | 파일을 직접 받는 경우 |

### Attr 은 어디서 주소를 읽을지 고르는 것

| Attr | 언제 쓰나 | 한 줄 설명 |
| --- | --- | --- |
| `href` | `a` 태그 주소를 읽을 때 | 링크 주소를 가져올 때 |
| `src` | `img`, `iframe` 같은 리소스 주소를 읽을 때 | 실제 리소스 주소를 가져올 때 |

### 가장 중요한 예외

- `href` 값이 `javascript:`로 시작하면 `src`로 바꾸지 말고, 먼저 그 링크가 뭘 하려는지 봐야 합니다.
- 화면 이동이나 팝업 열기처럼 "동작"이 목적이면 `click`을 씁니다.
- 파일 저장이 목적이면 `download`를 씁니다.
- `javascript:`는 실제 URL이 아니므로 `goto`에는 맞지 않습니다.
- 예: `ajaxFileDownLoad(...)`처럼 파일을 내려받는 링크는 `Action = download`, `Attr = href`가 맞습니다.

## 9. 실전 선택 기준

- 1순위는 "이 요소를 눌러야 하냐"입니다. 누르는 동작이 필요하면 `Action = click`입니다.
- 주소가 이미 보이면 `Action = goto`를 먼저 봅니다.
- 파일을 바로 받거나, 클릭하면 파일이 내려받아지는 링크면 `Action = download`를 씁니다.
- `Attr`은 URL이 어디에 들어 있는지만 봅니다. `a`면 보통 `href`, 이미지나 iframe이면 보통 `src`입니다.
- 본문 추출은 `Attr = text`, 구조 보존은 `Attr = html`이 기본입니다.

## 10. 빠른 예시

```json
{
  "name": "목록 상세 이동",
  "xpath": "/html/body/div[8]/div/div[3]/div[1]/table/tbody/tr[1]/td[2]/a",
  "action": "click",
  "open_mode": "popup",
  "wait_state": "attached"
}
```

```json
{
  "name": "링크 직접 이동",
  "xpath": "/html/body/div[8]/div/div[3]/div[1]/table/tbody/tr[1]/td[2]/a",
  "action": "goto",
  "attr": "href",
  "wait_state": "attached"
}
```

```json
{
  "name": "이미지 주소 열기",
  "xpath": "//img[@class='thumb']",
  "action": "goto",
  "attr": "src",
  "wait_state": "attached"
}
```

```json
{
  "name": "본문 추출",
  "xpath": "//*[@id='content']",
  "action": "extract",
  "attr": "text",
  "wait_state": "visible"
}
```

```json
{
  "name": "첨부파일 다운로드",
  "xpath": "//a[contains(@href, '.pdf')]",
  "action": "download",
  "attr": "href",
  "wait_state": "attached"
}
```
