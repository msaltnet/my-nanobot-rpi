# 역할별 작업 시작

아래 프롬프트의 `#123`과 SHA를 실제 값으로 바꾼다. Issue와 PR이 장기 컨텍스트이며,
각 역할은 [워크플로우](agentic-workflow.md)와 루트 AGENTS.md를 먼저 읽는다.
프롬프트를 저장한 것만으로 Agent가 자동 실행되지는 않는다.

## Planner

```text
Issue #123을 Planning해줘. AGENTS.md와 docs/project-direction.md를 읽고 현재 코드를 조사해.
기존 구현과 미래 제안을 구분하고 UX, 요구사항, Non-goals, 설계, 변경 파일·순서,
AC, 테스트, 관찰성, 배포·롤백·Dogfooding 계획을 Issue 본문에 반영해줘.
이 요청은 해당 Issue 본문 갱신과 기존 상태 라벨을 제거한 Planning 라벨 설정을 포함해.
제품·비용·설계 판단이 필요하면 핵심 질문만 하고 독립 조사는 계속해.
본문을 Human 검토 가능한 상태로 준비하고 승인 전에 구현하거나 Ready로 바꾸지 마.
```

## Human 설계 승인

```text
Issue #123의 현재 본문 설계와 AC를 승인해. 승인 근거를 Issue에 기록하고
기존 상태 라벨을 제거하고 Ready for Implementation 라벨을 적용해줘.
승인 범위 안에서 구현·테스트·Agent Review를 진행하고 모두 PASS면 PR을 만들어줘.
Tester와 Reviewer는 각각 별도 컨텍스트의 subagent로 검증해줘.
운영 배포는 후보 SHA와 롤백 계획을 준비한 후 내가 승인할게.
```

## Implementer

```text
Issue #123을 구현해줘. Issue 본문, Human 승인 근거, 상태 라벨을 먼저 확인해.
상태 라벨이 정확히 하나이며 Ready for Implementation인지 확인해.
라벨 누락·복수 상태·승인 불일치면 구현하지 말고 조사·Planning까지만 진행해.
열린 PR·기존 브랜치를 확인하고 승인 범위의 코드·테스트·문서를 변경해.
Tester와 Reviewer를 별도 컨텍스트의 subagent로 실행해 AC와 diff를 독립 확인해줘.
FAIL이면 구현·테스트·리뷰를 반복하고 현재 SHA에서 모두 PASS일 때 PR을 만들어줘.
PR 생성과 해당 Issue 진행 기록 갱신은 이 요청에 포함해. 설계 변경은 Human에게 돌아와.
배포·Merge는 별도 승인 전 실행하지 마.
```

## Tester (별도 컨텍스트에 전달)

```text
Issue #123의 승인 설계와 AC를 기준으로 후보 <SHA>를 독립 검증해줘.
구현자의 자기 평가를 근거로 삼지 말고 실제 코드·명령·사용자 흐름을 확인해.
정상·오류·경계·회귀를 검사하고 AC별 근거와 실행 명령·종료 코드를 보고해.
docs/development/verification-report-template.md 형식으로 PASS/FAIL/BLOCKED를 기록해.
실행하지 못한 항목을 PASS로 표시하지 말고 FAIL은 재현 절차와 함께 반환해.
이번 작업은 검증·보고이며 운영 배포나 코드 수정은 하지 마.
```

## Reviewer (별도 컨텍스트에 전달)

```text
Issue #123과 기준 <BASE_SHA> 대비 후보 <SHA> diff를 독립 리뷰해줘.
설계·범위 일치, 데이터 보존, 오류 처리, 시간대, 중복, 비용·자원, 보안,
동시성, 로그, 복잡성, 테스트 누락을 검토해.
docs/development/verification-report-template.md 형식으로 위치·근거·심각도를 보고해.
미해결 Critical/Major가 있으면 FAIL, 검토가 막히면 BLOCKED로 보고해.
Human 승인이나 배포·Merge를 대신하지 말고 검토한 SHA를 명시해.
```

## 후보 배포 승인

```text
PR #123의 후보 <SHA>를 내가 지정한 RPi 또는 OCI 대상과 Issue에 정한 범위에 배포하는 것을 승인해.
이전 SHA, 설정·DB 백업, 마이그레이션·롤백 절차를 먼저 확인하고 배포해줘.
승인된 smoke test를 수행하고 결과·명령·운영 상태를 PR에 기록해줘.
실제 서버 주소·개인 경로·비밀값은 공개 PR에서 제외하고 내 비공개 운영 기록으로 관리해.
이 요청은 후보 배포와 보고이며 Merge는 하지 마. 실사용 검수는 내가 할게.
```

## 수정 요청

```text
PR #123의 Human 피드백을 반영해줘. 구현 문제는 기존 Issue를 Ready로 유지하고
기존 PR에서 수정·독립 테스트·리뷰를 반복해. 설계 변경이면 Planning으로 돌리고
수정 설계를 Issue에 반영한 뒤 내 승인을 기다려.
승인된 배포 범위를 넘는 재배포와 Merge는 별도로 확인해.
```

## 최종 수용·Merge 승인

```text
PR #123의 <SHA>에 대한 PR 검토와 실사용 결과를 수용하며 Merge를 승인해.
현재 검증·리뷰·CI와 승인 이후 변경 여부를 확인하고 해당 PR을 병합해줘.
Issue Close를 확인하고 후보·최종 main·운영 버전 차이를 보고해줘.
최종 main 배포까지 Issue의 기존 배포 승인 범위에 포함되어 있으면 수행하고,
범위 밖이면 필요한 배포 작업을 정리해줘.
```

## 회고

```text
Issue #123의 설계, PR, 테스트·리뷰, 배포와 Dogfooding 기록을 바탕으로 회고해줘.
기대·실제 결과·배운 점·다음 결정을 docs/development/lifecycle-report-template.md로 정리해.
후속 개선은 새 Open Issue 초안으로, AX Notes는 사실 근거가 있는 소재 초안으로 작성해.
외부 게시와 후속 Issue 생성은 초안 검토 후 내가 지시할게.
```
