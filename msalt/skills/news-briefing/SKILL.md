---
name: news-briefing
description: 정기 경제 뉴스 브리핑을 생성합니다. 크론 스케줄러가 사용합니다.
metadata: {"always": false}
---

# 정기 뉴스 브리핑

크론 스케줄러에 의해 실행됩니다. 다음 단계를 수행하세요. (`python -m …` / `python3 -m …` 형태는 venv 외부 인터프리터로 풀려 `ModuleNotFoundError`가 나니 금지.)

1. 뉴스 수집 실행:
```bash
msalt-nanobot news collect
```

2. 브리핑 생성 (저녁이면 `evening` 인자):
```bash
msalt-nanobot news briefing
msalt-nanobot news briefing evening
```

3. 결과를 사용자에게 전달하세요.
