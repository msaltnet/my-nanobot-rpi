---
name: news-briefing
description: 정기 경제 뉴스 브리핑을 생성합니다. 크론 스케줄러가 사용합니다.
metadata: {"always": false}
---

# 정기 뉴스 브리핑

크론 스케줄러에 의해 실행됩니다. 다음 단계를 수행하세요:

1. 뉴스 수집 실행:
```bash
python -m msalt.news.cli collect
```

2. 브리핑 생성:
```bash
python -m msalt.news.cli briefing
```

3. 결과를 사용자에게 전달하세요.
