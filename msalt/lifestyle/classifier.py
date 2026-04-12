"""자유 텍스트를 카테고리로 분류한다."""

CATEGORY_KEYWORDS = {
    "exercise": ["달리", "달림", "운동", "헬스", "수영", "자전거", "걸음", "산책", "스쿼트",
                  "푸시업", "플랭크", "요가", "등산", "km", "러닝"],
    "food": ["먹", "마심", "마셨", "식사", "아침", "점심", "저녁", "간식", "커피", "음식",
             "밥", "라면", "치킨", "피자", "샐러드"],
    "health": ["약", "병원", "두통", "감기", "열", "통증", "진료", "체중", "혈압",
               "컨디션", "피곤", "아프"],
    "mood": ["기분", "행복", "우울", "화남", "짜증", "좋음", "슬픔", "스트레스",
             "불안", "편안", "즐거"],
    "sleep": ["잠", "수면", "잤", "일어", "기상", "취침", "낮잠"],
}


def classify_text(text: str) -> dict:
    """텍스트를 카테고리로 분류하고, 파싱된 데이터를 반환한다."""
    text_lower = text.lower()

    best_category = "other"
    best_score = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_category = category

    return {
        "category": best_category,
        "parsed_data": {"detail": text, "confidence": "keyword"},
    }
