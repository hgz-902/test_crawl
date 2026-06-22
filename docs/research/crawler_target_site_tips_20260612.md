# 수집 대상 사이트별 크롤링 참고 팁

조사일: 2026-06-12

이 문서는 크롤링 참고 사이트와 공식 문서에서 확인한 내용을 대상별로 재분류한 것이다. 각 항목은 해당 참고 사이트가 설명한 수집 가능 데이터, 입력 방식, 제한, 주의 사항을 요약한 것이다.

## 참고한 사이트

- Apify Social Media Scrapers: https://apify.com/store/categories/social-media
- Apify Instagram Scraper: https://apify.com/apify/instagram-scraper
- Apify Instagram Post Scraper: https://apify.com/apify/instagram-post-scraper
- Apify Instagram Search Scraper: https://apify.com/apify/instagram-search-scraper
- Apify Instagram Comments Scraper: https://apify.com/apify/instagram-comment-scraper
- Apify Instagram Hashtag Analytics Scraper: https://apify.com/apify/instagram-hashtag-analytics-scraper
- Apify Facebook Pages Scraper: https://apify.com/apify/facebook-pages-scraper
- Apify Facebook Posts Scraper: https://apify.com/apify/facebook-posts-scraper
- Apify Facebook Comments Scraper: https://apify.com/apify/facebook-comments-scraper
- Apify Facebook Groups Scraper: https://apify.com/apify/facebook-groups-scraper
- Apify Twitter/X Scraper: https://apify.com/scrapers/twitter
- Bright Data Social Media Scraper: https://brightdata.com/products/web-scraper/social-media-scrape
- Bright Data Twitter Scraper: https://brightdata.com/products/web-scraper/twitter
- Bright Data Twitter Profile Scraper: https://brightdata.com/products/web-scraper/twitter/profile
- Bright Data Hashtag Scraper: https://brightdata.com/products/web-scraper/hashtag
- Bright Data Instagram Reels Scraper: https://brightdata.com/products/web-scraper/instagram/reels
- Bright Data Facebook Reels Scraper: https://brightdata.com/products/web-scraper/facebook/reels
- Bright Data YouTube Shorts Scraper: https://brightdata.com/products/web-scraper/youtube/shorts
- Bright Data Web Scraper: https://brightdata.com/products/web-scraper
- Bright Data Social Media Scraper API Docs: https://docs.brightdata.com/api-reference/scrapers/social-media-apis/overview
- Zyte Web Scraping Best Practices: https://www.zyte.com/learn/web-scraping-best-practices/
- Zyte Web Scraping Project Elements: https://www.zyte.com/learn/what-are-the-elements-of-a-web-scraping-project/
- Oxylabs Web Scraping Best Practices: https://oxylabs.io/blog/web-scraping-best-practices
- ScrapingBee robots.txt guide: https://www.scrapingbee.com/blog/robots-txt-web-scraping/
- ScraperAPI Social Media Scraper: https://www.scraperapi.com/web-scraping/social-media-scraper/
- Naver Search API News: https://developers.naver.com/docs/serviceapi/search/news/news.md
- Naver Search API Blog: https://developers.naver.com/docs/serviceapi/search/blog/blog.md
- Naver Search Advisor robots.txt guide: https://searchadvisor.naver.com/guide/seo-basic-robots
- Instagram Graph API Hashtag Search: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/hashtag-search/
- Instagram Platform: https://developers.facebook.com/docs/instagram-platform/
- Meta Page Public Content Access: https://developers.facebook.com/docs/features-reference/page-public-content-access/
- Meta Automated Data Collection: https://developers.facebook.com/docs/development/terms-and-policies/automated-data-collection/
- Meta Content Library/API: https://transparency.meta.com/researchtools/meta-content-library/
- X Developer Guidelines: https://docs.x.com/developer-guidelines
- X API Rate Limits: https://docs.x.com/x-api/fundamentals/rate-limits
- X API Pricing: https://docs.x.com/x-api/getting-started/pricing

## 1. 일반 웹사이트

참고 출처:

- Zyte Web Scraping Best Practices
- Zyte Web Scraping Project Elements
- Oxylabs Web Scraping Best Practices
- ScrapingBee robots.txt guide
- Bright Data Web Scraper

수집 팁:

- 대상 웹사이트에 부담을 주지 않는 것이 첫 번째 원칙이다.
- 같은 사이트에 대한 동시 요청 수를 제한한다.
- robots.txt의 crawl-delay가 있으면 요청 간격에 반영한다.
- 가능하면 사이트의 비피크 시간대에 수집한다.
- 사이트 운영자가 연락할 수 있도록 식별 가능한 user-agent 또는 연락 경로를 제공하는 방식이 권장된다.
- robots.txt를 먼저 확인해 어떤 경로가 허용/차단되는지 본다.
- 로그인 뒤에 접근하는 페이지는 약관 동의와 연결될 수 있으므로 특히 주의한다.
- 사이트 레이아웃 변경, 데이터 품질, proxy 필요성, 유지보수 계획까지 포함해 scraping project를 설계해야 한다.
- 대규모 수집에서는 proxy management가 필요할 수 있다.
- proxy만 늘린다고 모든 scaling 문제가 해결되는 것은 아니며, 대상 사이트의 트래픽 규모와 요청량을 함께 고려해야 한다.
- scraping이 핵심 사업 영역이 아니라면 proxy management를 직접 구현하는 대신 managed proxy 또는 scraping API를 쓰는 선택지도 있다.
- 429 또는 차단이 발생하면 요청 속도, proxy, user-agent, browser rendering 필요성을 재검토한다.
- Oxylabs는 proxy rotation을 통해 단일 IP에 요청이 누적되지 않도록 하는 방식을 설명한다.
- Bright Data는 API 기반 scraper, no-code scraper, scheduler, 데이터 전달 방식을 제공한다고 설명한다.

## 2. 네이버

참고 출처:

- Naver Search API News
- Naver Search API Blog
- Naver Search Advisor robots.txt guide

수집 팁:

- 네이버 뉴스 검색은 Naver Search API를 통해 XML 또는 JSON 형식으로 받을 수 있다.
- 뉴스 검색 API는 검색어와 검색 조건을 query string으로 전달한다.
- Naver Search API는 비로그인 방식 Open API다.
- API 호출 시 HTTP header에 Client ID와 Client Secret을 포함한다.
- 뉴스 검색 API는 하루 호출 한도 25,000회를 갖는다.
- API 사용량은 Client ID별로 합산된다.
- 블로그 검색도 Naver Search API로 XML 또는 JSON 결과를 받을 수 있다.
- Naver Search Advisor 문서는 robots.txt를 통해 검색 로봇의 수집 가능 여부를 확인하라고 안내한다.
- Naver 수집 요청 API를 사용할 때도 대상 URL은 네이버 검색 로봇이 수집할 수 있어야 한다.

주의 사항:

- API key/secret은 코드나 로그에 직접 노출하지 않는다.
- 하루 호출 한도와 Client ID별 합산 기준을 고려해 호출량을 관리한다.

## 3. Instagram

참고 출처:

- Instagram Graph API Hashtag Search
- Instagram Platform
- Meta Automated Data Collection
- Meta Content Library/API
- Apify Instagram Scraper
- Apify Instagram Post Scraper
- Apify Instagram Search Scraper
- Apify Instagram Comments Scraper
- Apify Instagram Hashtag Analytics Scraper
- Bright Data Instagram Reels Scraper

공식 API 팁:

- Instagram Platform은 Instagram Business 또는 Creator 계정과 Facebook Page 연결을 요구하는 기능이 있다.
- Hashtag Search API는 Instagram Business 또는 Creator 계정 기준 rolling 7일 동안 최대 30개 unique hashtag를 query할 수 있다.
- 한 번 query한 hashtag는 7일 제한에 포함된다.
- Meta 문서는 자동 데이터 수집을 사전 허가 또는 명시적으로 허용된 수단 안에서 수행해야 한다고 설명한다.
- Meta Content Library/API는 Facebook, Instagram 등의 공개 콘텐츠 archive 접근을 위한 연구 도구로 소개된다.
- Meta Content Library/API는 일반 상용 scraping 도구가 아니라 접근 자격이 필요한 연구 도구로 다뤄진다.

Apify Instagram Scraper 팁:

- profile page, hashtag page, place 기반으로 post를 수집할 수 있다고 설명한다.
- Instagram post URL을 입력하면 comment scraping도 가능하다고 설명한다.
- profile scraping은 post 수집 또는 profile metadata 수집으로 나뉜다.
- hashtag scraping은 keyword와 일치하는 hashtag를 query하고, post 또는 hashtag metadata를 수집할 수 있다고 설명한다.
- place/location scraping은 keyword와 일치하는 장소를 query하고 post 또는 place metadata를 수집할 수 있다고 설명한다.
- comment scraping은 post 기준으로 comment를 수집할 수 있다고 설명한다.
- 입력은 Instagram page URL 목록 또는 search query를 포함하는 JSON으로 구성된다.
- 결과는 dataset에 item 단위로 저장된다.
- 결과 수는 입력의 복잡도, 위치, 접근 가능 상태 등에 따라 달라질 수 있으며, incognito browser에서 비로그인 사용자에게 보이는 범위를 확인하는 방법을 제안한다.
- scraper 실행 중 현재 어떤 page를 scraping하는지, 몇 개 item이 load되었는지 log message로 표시된다고 설명한다.
- 잘못된 input은 즉시 failure state와 설명을 출력한다고 설명한다.
- 결과는 JSON, CSV, Excel 등으로 export하거나 API로 사용할 수 있다고 설명한다.

Apify Instagram Post/Search/Comment/Hashtag 도구 팁:

- Instagram Post Scraper는 public profile, username, profile URL, post URL을 입력으로 받아 public post data를 추출한다고 설명한다.
- post data에는 caption, mention, image, tagged user, likes, comments, replies, video views 같은 항목이 포함될 수 있다고 설명한다.
- Instagram Search Scraper는 public data만 수집하고 private content는 접근하지 않는다고 설명한다.
- Instagram Comment Scraper는 공개적으로 공유된 comment data를 대상으로 한다고 설명한다.
- Instagram Hashtag Analytics Scraper는 hashtag를 하나씩 입력하거나 prepared list를 붙여넣거나 API로 입력할 수 있다고 설명한다.

Bright Data Instagram/Reels 팁:

- Instagram Reels Scraper는 URL, username, description, hashtags, comment 수, like 수, view 수 등을 수집한다고 설명한다.
- API 기반 scraper 또는 no-code scraper 방식으로 사용할 수 있다고 설명한다.
- 대량 처리, 결과 전달, 다양한 형식의 결과 반환을 강조한다.

법적/개인정보 주의:

- Apify는 private user data를 추출하지 않고 사용자가 공개한 데이터만 추출한다고 설명한다.
- Apify는 공개 데이터라도 개인정보가 포함될 수 있고 GDPR 등 개인정보 규제 대상이 될 수 있으므로 정당한 이유가 필요하다고 설명한다.

## 4. Facebook

참고 출처:

- Meta Page Public Content Access
- Meta Automated Data Collection
- Meta Content Library/API
- Apify Facebook Pages Scraper
- Apify Facebook Posts Scraper
- Apify Facebook Comments Scraper
- Apify Facebook Groups Scraper
- Bright Data Facebook Reels Scraper

공식 API/정책 팁:

- Page Public Content Access는 Pages Search API 접근과, 앱이 직접 관리하지 않는 Page의 public data 읽기와 관련된 기능으로 설명된다.
- Facebook Page public content를 API로 가져오려면 권한과 app review가 필요할 수 있다.
- Meta 문서는 자동 데이터 수집을 Platform API 또는 사전 허가된 방식으로 제한한다고 설명한다.
- Meta Content Library/API는 Facebook과 Instagram의 공개 콘텐츠 archive를 연구 목적으로 접근하는 도구로 소개된다.

Apify Facebook Pages Scraper 팁:

- 여러 Facebook Page 또는 Profile의 basic data를 추출할 수 있다고 설명한다.
- 추출 대상 예시는 website, email, address, Messenger, likes, followers, rating, ads running status 등이다.
- 사용 방법은 Apify 계정 생성, scraper 열기, 하나 이상의 Facebook Page URL 입력, 실행, JSON/XML/CSV/Excel/HTML 다운로드 순서로 설명된다.
- API, scheduler, integration workflow와 연결할 수 있다고 설명한다.

Apify Facebook Posts Scraper 팁:

- 입력은 Facebook page URL 또는 profile URL이다.
- URL을 하나씩 넣거나 prepared list를 붙여넣거나 API로 설정할 수 있다고 설명한다.
- optional filter로 custom date range 같은 time frame을 지정할 수 있다고 설명한다.
- video transcripts 사용 또는 post 수 제한 설정이 가능하다고 설명한다.
- 수집 대상은 posts, videos, engagement metrics, text captions, reactions, media, external links 등으로 설명된다.

Apify Facebook Comments Scraper 팁:

- 하나 또는 여러 Facebook post에서 comment data를 수집할 수 있다고 설명한다.
- comment text, timestamp, likes count, basic commenter info를 가져올 수 있다고 설명한다.
- JSON, CSV, Excel로 다운로드해 app, spreadsheet, report에서 사용할 수 있다고 설명한다.

Apify Facebook Groups Scraper 팁:

- 하나 또는 여러 public Facebook group에서 data를 추출할 수 있다고 설명한다.
- group URL, post URL, post text, comments, timestamp, likes/comment count, basic commentator info를 가져올 수 있다고 설명한다.
- JSON, CSV, Excel로 다운로드할 수 있다고 설명한다.

Bright Data Facebook/Reels 팁:

- Facebook Reels Scraper는 URL, post ID, username, content, date posted, hashtags, likes, comments, shares 등을 수집할 수 있다고 설명한다.
- API 기반 scraper와 no-code scraper 방식을 제공한다고 설명한다.

주의 사항:

- Facebook 관련 데이터에는 comment, profile, group 정보 등 개인정보 성격의 데이터가 섞일 수 있으므로 수집 목적과 저장 범위를 검토해야 한다.
- Meta의 자동 데이터 수집 정책과 Graph API 권한 조건을 함께 확인해야 한다.

## 5. X / Twitter

참고 출처:

- X Developer Guidelines
- X API Rate Limits
- X API Pricing
- Apify Twitter/X Scraper
- Bright Data Twitter Scraper
- Bright Data Twitter Profile Scraper

공식 API/정책 팁:

- X Developer Guidelines는 non-API automation, scraping, browser automation을 금지된 활동으로 설명한다.
- 위반 시 app suspension, API access revocation, account ban 가능성이 있다고 설명한다.
- X API의 rate limit은 endpoint와 tier별로 다르다.
- 429 응답을 받으면 rate limit exceeded로 보고 `x-rate-limit-reset` header를 확인해야 한다.
- rate limit 복구 전략은 reset time까지 기다리고 필요하면 exponential backoff를 사용하는 것이다.
- X API best practice로 response caching, streaming 사용, header monitoring, time window 내 request 분산이 제시된다.
- X API는 pay-per-use 구조이며, rate limit과 billing은 별개의 개념으로 설명된다.
- X data를 표시할 때는 attribution, branding, content deletion 반영, metadata 보존 같은 정책 요구가 있다.
- 삭제 요청, 사용자 삭제 요청, content suspension/removal, API access termination 시 정해진 기한 내 삭제가 필요하다고 설명한다.
- API credentials와 token은 환경변수나 secret manager에 보관하라고 설명한다.

Apify Twitter/X Scraper 팁:

- real-time 및 historical Twitter data를 가져올 수 있다고 설명한다.
- JSON, CSV, Excel, API export를 지원한다고 설명한다.
- run을 automate, schedule, monitor할 수 있다고 설명한다.
- tweets, profiles, trending topics 등을 수집하는 도구들이 있다고 설명한다.

Bright Data Twitter 팁:

- Twitter Scraper는 URL, hashtag, image, video, tweet, retweet, conversation thread, follower/following, location 등을 포함한 public data 수집을 설명한다.
- Twitter Profile Scraper는 profile 중심으로 bio, tweet history, follower count, engagement pattern 등을 수집한다고 설명한다.
- API 또는 no-code scraper로 사용할 수 있다고 설명한다.
- bulk request handling, 다양한 output format을 제공한다고 설명한다.

주의 사항:

- X는 공식 문서에서 scraping/browser automation 금지를 강하게 명시하므로, 상용 scraper 설명과 공식 정책을 함께 검토해야 한다.
- rate limit을 우회하기 위해 여러 app을 만들거나 제한을 회피하는 방식은 금지 활동으로 설명된다.

## 6. TikTok

참고 출처:

- Bright Data Social Media Scraper
- Bright Data Social Media Scraper API Docs
- ScraperAPI Social Media Scraper
- Apify Social Media Scrapers

수집 팁:

- Bright Data는 TikTok을 social media scraper 지원 플랫폼 중 하나로 설명한다.
- profile, posts, comments 같은 social media data 유형을 수집하는 API 범주 안에 포함된다.
- Bright Data는 influencer 파악을 위해 follower count, post engagement rate, likes, video view count, verification status 같은 profile data를 수집할 수 있다고 설명한다.
- ScraperAPI는 social media scraping에서 CAPTCHA handling, IP rotation, JavaScript rendering, real-time data collection 같은 기능을 비교 포인트로 제시한다.

주의 사항:

- TikTok 관련 공식 API/정책 문서는 이번 참고 목록에서 직접 확인한 범위가 제한적이다.
- 상용 scraper 자료는 수집 가능성을 설명하지만, 실제 운영 전 TikTok 공식 정책과 개인정보 기준을 따로 확인해야 한다.

## 7. YouTube / YouTube Shorts

참고 출처:

- Bright Data Social Media Scraper
- Bright Data YouTube Shorts Scraper

수집 팁:

- Bright Data는 YouTube를 social media scraper 지원 플랫폼 중 하나로 설명한다.
- YouTube Shorts Scraper는 short ID, title, views, likes, URL, creator handle, comments 등을 수집할 수 있다고 설명한다.
- API 기반 scraper와 no-code scraper 방식을 제공한다고 설명한다.
- scheduler로 수집 빈도를 제어하고, 결과를 원하는 storage로 전달하거나 다운로드할 수 있다고 설명한다.

주의 사항:

- 댓글과 creator 관련 데이터는 개인정보 또는 계정 정보와 연결될 수 있으므로 저장 범위를 검토해야 한다.
- YouTube 공식 API quota와 약관은 별도로 확인해야 한다.

## 8. LinkedIn

참고 출처:

- Bright Data Social Media Scraper API Docs
- Bright Data Web Scraper
- ScraperAPI Social Media Scraper
- Apify Social Media Scrapers

수집 팁:

- Bright Data Social Media Scraper API Docs는 LinkedIn을 지원 social platform 중 하나로 언급한다.
- Bright Data Web Scraper는 LinkedIn Scraper를 top scraper API 범주에 포함해 설명한다.
- ScraperAPI는 social media scraper 비교에서 LinkedIn 같은 플랫폼 수집을 예시로 든다.
- social media scraper 선택 기준으로 proxy, CAPTCHA handling, JavaScript rendering, real-time collection, pricing, ease of use가 제시된다.

주의 사항:

- LinkedIn은 로그인/계정/프로필 정보와 연결될 가능성이 높으므로 공식 API/약관/개인정보 기준 확인이 필요하다.
- 이번 참고 목록에서는 LinkedIn 개별 공식 API 제한은 확인하지 않았다.

## 9. Hashtag / Social hashtag 수집

참고 출처:

- Bright Data Hashtag Scraper
- Apify Instagram Hashtag Analytics Scraper
- Instagram Graph API Hashtag Search

수집 팁:

- Bright Data Hashtag Scraper는 여러 social media website에서 hashtag를 수집하고 posts, comments, images, likes count, locations, timestamps 등을 추출할 수 있다고 설명한다.
- API 또는 no-code scraper로 사용할 수 있다고 설명한다.
- bulk request와 다양한 결과 포맷을 제공한다고 설명한다.
- Apify Instagram Hashtag Analytics Scraper는 hashtag를 하나씩 입력하거나 list를 붙여넣거나 API로 입력할 수 있다고 설명한다.
- Instagram 공식 Hashtag Search는 rolling 7일 동안 최대 30개 unique hashtag 제한이 있다.

주의 사항:

- hashtag 수집은 platform별 제한이 다르므로 Instagram 공식 제한을 다른 SNS에 그대로 적용하면 안 된다.
- comment/location/timestamp는 개인정보 또는 민감 맥락이 될 수 있으므로 저장 범위를 검토해야 한다.

## 10. Social media 전체

참고 출처:

- Apify Social Media Scrapers
- Bright Data Social Media Scraper
- Bright Data Social Media Scraper API Docs
- ScraperAPI Social Media Scraper
- ScrapingBee Social Media Scraper API repository

수집 팁:

- Apify는 social media scraper를 통해 pages, trending posts, profiles, comments, reviews, engagement를 추적할 수 있다고 설명한다.
- Apify는 scraper 실행 결과를 JSON, CSV, Excel 또는 API로 export하고, schedule 및 monitor할 수 있다고 설명한다.
- Bright Data는 Facebook, Twitter/X, Instagram, TikTok, YouTube 등 major social media platform의 public data를 API 또는 no-code scraper로 수집할 수 있다고 설명한다.
- Bright Data는 proxy server나 block 대응 infrastructure를 직접 관리하지 않아도 된다는 점을 강조한다.
- Bright Data는 profile, posts, reels, jobs, events, comments 등 data type별 endpoint를 제공한다고 설명한다.
- Bright Data는 bulk request handling과 다양한 output format을 설명한다.
- ScraperAPI는 social media scraper 비교 기준으로 CAPTCHA 처리, IP rotation, JavaScript rendering, real-time collection, 가격, 사용 편의성, reliability를 제시한다.
- ScrapingBee는 social media scraper API가 proxy rotation, headless browser, anti-bot system 처리를 단일 HTTP request 뒤에서 처리한다고 설명한다.

주의 사항:

- 상용 scraper는 기술적 편의와 안정성을 제공하지만, 각 platform의 공식 정책과 법적 리스크를 제거해주지는 않는다.
- SNS 데이터는 공개 데이터라도 개인정보가 포함될 수 있다.

## 11. Amazon / Google SERP / Google Maps / eCommerce 등 일반 상용 scraper 대상

참고 출처:

- Apify Web Scrapers
- Bright Data Web Scraper
- Bright Data Web Scraper API

수집 팁:

- Apify는 Amazon scraper, Google SERP scraper, Twitter/X scraper 등 다양한 pre-built scraper를 제공한다고 설명한다.
- Bright Data는 600개 이상의 ready-made scraper와 Web Scraper API를 제공한다고 설명한다.
- Bright Data는 no-code interface, API scraper, scheduler, preferred storage delivery를 제공한다고 설명한다.
- Bright Data는 pay only for successfully delivered results 또는 성공 결과 기반 과금을 강조한다.
- Bright Data는 bulk request handling을 지원한다고 설명한다.

주의 사항:

- eCommerce, 지도, 검색 결과는 가격, 리뷰, 위치, 업체 정보 등 민감한 상업 데이터가 포함될 수 있으므로 대상 사이트 정책을 확인해야 한다.
- 검색 결과/지도/상거래 사이트는 anti-bot과 rate limit이 강한 경우가 많으므로 상용 scraper API가 대안으로 제시된다.

## 12. 공식 API를 우선 검토해야 하는 대상

참고 출처:

- Naver Search API
- Instagram Graph API
- Meta Page Public Content Access
- Meta Content Library/API
- X Developer Guidelines
- X API Rate Limits

대상별 공식 API 관련 팁:

- Naver: 뉴스/블로그 검색은 Search API로 XML/JSON 결과를 받을 수 있고 하루 호출 한도 25,000회가 있다.
- Instagram: Business/Creator 계정 기반 Graph API 기능이 있으며 hashtag search는 30개 unique hashtag/7일 제한이 있다.
- Facebook: Page Public Content Access는 앱이 직접 관리하지 않는 Page public data 접근과 관련되며 app review가 필요할 수 있다.
- Meta 연구 데이터: Meta Content Library/API는 Facebook/Instagram 공개 콘텐츠 archive 접근을 위한 연구 도구로 제공된다.
- X: non-API scraping/browser automation을 금지한다고 설명하며 공식 X API 사용을 요구한다.

## 13. 출력 형식 / 운영 기능 관련 팁

참고 출처:

- Apify Instagram/Facebook/Twitter scraper pages
- Bright Data Social Media Scraper
- Bright Data Web Scraper

팁:

- Apify scraper들은 JSON, CSV, Excel, HTML, API export 등을 지원한다고 설명한다.
- Apify는 scraper run을 schedule하고 monitor할 수 있다고 설명한다.
- Apify는 잘못된 input에 대해 failure state와 설명을 출력한다고 설명한다.
- Bright Data는 API 기반 scraper, no-code scraper, scheduler, storage delivery를 제공한다고 설명한다.
- Bright Data는 bulk request handling과 다양한 format 반환을 강조한다.

## 14. 법적/정책/개인정보 관련 팁

참고 출처:

- Apify Instagram Scraper
- Apify Instagram Search Scraper
- Meta Automated Data Collection
- X Developer Guidelines
- Zyte Web Scraping Best Practices
- Zyte Web Scraping Project Elements

팁:

- Apify는 Instagram scraper가 private user data를 추출하지 않고 공개 데이터만 대상으로 한다고 설명한다.
- Apify는 공개 데이터에도 개인정보가 포함될 수 있으며 GDPR 등 개인정보 규제 대상이 될 수 있다고 설명한다.
- Apify는 개인정보를 scrape할 정당한 이유가 필요하며 불확실하면 법률 자문을 구하라고 설명한다.
- Meta는 자동 데이터 수집은 사전 허가 또는 명시적으로 허용된 수단이어야 한다고 설명한다.
- X는 non-API automation, scraping, browser automation을 금지한다고 설명한다.
- Zyte는 로그인 뒤 페이지 scraping은 약관 동의와 연결될 수 있으므로 조심해야 한다고 설명한다.
- robots.txt는 먼저 확인해야 하며, crawl-delay가 있으면 반영하는 것이 권장된다.

## 15. 요약 표

| 수집 대상 | 참고 사이트에서 확인한 주요 수집 방식 | 주요 팁/제한 |
|---|---|---|
| 일반 웹사이트 | HTML scraping, browser rendering, scraping API | robots.txt 확인, 요청량 제한, crawl-delay 반영, user-agent 식별 |
| 네이버 뉴스/블로그 | Naver Search API | XML/JSON 제공, Client ID/Secret 필요, 뉴스 검색 하루 25,000회 한도 |
| Instagram | Graph API, Meta Content Library, 상용 scraper | hashtag 30개/7일 제한, Business/Creator 계정, 공개 데이터라도 개인정보 주의 |
| Facebook | Graph API, Page Public Content Access, Meta Content Library, 상용 scraper | Page 권한/app review 가능성, comments/profile/group 정보 개인정보 주의 |
| X/Twitter | X API, 상용 scraper | 공식 문서상 non-API scraping/browser automation 금지, 429 reset header/backoff 필요 |
| TikTok | 상용 social media scraper | CAPTCHA/IP rotation/JS rendering 등 anti-bot 처리 비교 필요 |
| YouTube Shorts | Bright Data scraper | short ID, title, views, likes, comments 등 수집 가능 설명 |
| LinkedIn | 상용 social media scraper | 로그인/프로필 정보 정책 확인 필요 |
| Hashtag | Instagram Hashtag API, hashtag scraper | Instagram은 30 unique hashtag/7일 제한 |
| Amazon/Google SERP/Google Maps/eCommerce | pre-built web scraper/API | anti-bot, bulk request, 성공 결과 기반 과금 등 확인 |
