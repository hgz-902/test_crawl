from __future__ import annotations

from typing import Any

from crawler_app.news_sqlite_store import unanalyzed_article_titles, upsert_batch_sentiments


MODEL_NAME = "knu_sentiment_dict_v1"

POSITIVE_WORDS = {
    "호조", "상승", "증가", "성장", "호실적", "개선", "돌파", "흑자", "수혜", "급등",
    "최고", "최대", "사상최대", "신기록", "반등", "회복", "활황", "호황", "확대", "강세",
    "수익", "이익", "영업이익", "순이익", "매출증가", "실적개선", "턴어라운드",
    "성공", "혁신", "달성", "수주", "계약", "협력", "제휴", "투자", "인수", "합병",
    "출시", "론칭", "확장", "진출", "선정", "수상", "1위", "선두", "독보적",
    "개발", "특허", "기술력", "친환경", "탄소중립", "AI", "디지털전환",
    "기대", "낙관", "호평", "긍정적", "우호적", "안정", "강화", "지원", "촉진",
    "축하", "환영", "쾌거", "약진", "도약", "비상", "승승장구",
}

NEGATIVE_WORDS = {
    "하락", "감소", "적자", "부진", "손실", "폭락", "급락", "침체", "불황", "위축",
    "최저", "최약", "역대최저", "둔화", "축소", "감산", "영업손실", "순손실", "적자전환",
    "위기", "리스크", "우려", "불안", "경고", "위험", "파산", "부도", "채무불이행",
    "디폴트", "모라토리엄", "구조조정", "감원", "해고", "퇴출", "폐업", "파업",
    "논란", "의혹", "비리", "횡령", "배임", "사기", "탈세", "위반", "제재", "벌금",
    "과징금", "소송", "고발", "기소", "구속", "체포", "수사", "조사", "처벌",
    "사고", "폭발", "화재", "피해", "재해", "유출", "오염", "결함", "리콜",
    "실패", "좌절", "중단", "철수", "포기", "취소", "연기", "지연", "차질",
    "갈등", "분쟁", "마찰", "반발", "저항", "비판", "비난", "질타",
}


# 개발팀 공유 노트북의 키워드 기반 감성분석을 로컬 SQLite용으로 수행한다.
def analyze_sentiment(title: str, body: str = "") -> dict[str, Any]:
    text = "\n".join(part.strip() for part in (title or "", body or "") if part and part.strip()).strip()
    if not text:
        return {"sentiment": "neutral", "confidence": 0.5}

    pos_count = sum(1 for word in POSITIVE_WORDS if word in text)
    neg_count = sum(1 for word in NEGATIVE_WORDS if word in text)
    total = pos_count + neg_count
    if total == 0:
        return {"sentiment": "neutral", "confidence": 0.5}

    pos_ratio = pos_count / total
    neg_ratio = neg_count / total
    if pos_ratio > neg_ratio:
        return {"sentiment": "positive", "confidence": round(0.5 + (pos_ratio - neg_ratio) * 0.5, 4)}
    if neg_ratio > pos_ratio:
        return {"sentiment": "negative", "confidence": round(0.5 + (neg_ratio - pos_ratio) * 0.5, 4)}
    return {"sentiment": "neutral", "confidence": 0.5}


# article_sentiment에 없는 기사만 batch 감성분석 결과로 채운다.
def analyze_unanalyzed_articles(conn: Any) -> int:
    articles = unanalyzed_article_titles(conn)
    rows: list[dict[str, Any]] = []
    for article in articles:
        result = analyze_sentiment(str(article.get("title") or ""), str(article.get("body") or ""))
        rows.append(
            {
                "article_id": article["article_id"],
                "sentiment": result["sentiment"],
                "confidence": result["confidence"],
                "model_name": MODEL_NAME,
                "sentiment_source": "batch",
            }
        )
    return upsert_batch_sentiments(conn, rows)
