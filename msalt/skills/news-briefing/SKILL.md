---
name: news-briefing
description: 정기 경제 뉴스 브리핑을 생성합니다. 크론 스케줄러가 사용합니다.
metadata: {"always": false}
---

# 정기 뉴스 브리핑

크론 스케줄러에 의해 실행됩니다. 해당 시각의 브리핑 명령 **하나만** 실행하세요. 각 브리핑 명령이 뉴스 수집을 1회 수행한 뒤 브리핑을 생성합니다. (`python -m …` / `python3 -m …` 형태는 venv 외부 인터프리터로 풀려 `ModuleNotFoundError`가 나니 금지.)

1. 브리핑 생성 (점심은 `afternoon`, 저녁은 `evening` 인자):
```bash
my-nanobot-rpi news briefing
my-nanobot-rpi news briefing afternoon
my-nanobot-rpi news briefing evening
```

2. 결과를 사용자에게 전달하세요. 이번 수집이 0건이어도 기존 DB에 선택 가능한 기사가 있으면 브리핑에 포함될 수 있습니다. 빈 기사 안내나 오류가 나와도 수집 또는 브리핑을 임의로 반복하지 말고 그 상태를 남기세요.
