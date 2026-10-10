---
name: news-briefing
description: 정기 아침·점심·저녁 경제 뉴스 브리핑 요청과 해당 크론 작업에 사용합니다.
metadata: {"always": false}
---

# 정기 뉴스 브리핑

요청 시각에 해당하는 `news_briefing` 도구를 정확히 한 번 호출하세요.
아침은 morning, 점심은 afternoon, 저녁은 evening입니다. 아래 예 중 하나만 선택합니다.

```json
{"name":"news_briefing","arguments":{"time_of_day":"morning"}}
```

```json
{"name":"news_briefing","arguments":{"time_of_day":"afternoon"}}
```

```json
{"name":"news_briefing","arguments":{"time_of_day":"evening"}}
```

도구가 수집 1회, 생성, 원장 기록과 전용 전달을 담당합니다. 반환값은 status와 delivery_id뿐입니다.
도구 호출 뒤에는 종료하세요. 성공·빈 기사·중복 슬롯·기발송·failed·unknown·unavailable 모두 본문을 복사하거나 일반 응답/message/exec로 다시 보내지 않습니다.

수집 명령 또는 CLI 미리보기 명령을 선행하거나 반복하지 마세요. 도구 미등록/unsupported/denied여도 우회 전달하지 마세요.
재시도, 수신 확인, 포기, 재생성은 운영자 CLI의 명시적 판단이며 이 스킬이나 모델의 권한이 아닙니다.
