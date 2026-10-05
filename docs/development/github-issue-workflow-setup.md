# Issue 상태 관리

대상 저장소: `msaltnet/my-nanobot-rpi`. [개발 워크플로우](agentic-workflow.md)를 따른다.
Projects 보드 없이 Issue 라벨로 개발 상태를 관리한다. Projects 권한은 요구하지 않는다.
앱을 설치하는 사용자가 이 개발 절차에 참여할 필요는 없다.

## 상태 기준

| 라벨 | 의미 | 가능한 작업 |
|---|---|---|
| `Open` | 아이디어·문제 발견 | 기록·초기 조사 |
| `Planning` | 설계 구체화·Human 승인 대기 | 조사·계획·설계 수정 |
| `Ready for Implementation` | 현재 Issue 본문 설계의 Human 승인 확인 | 승인 범위 구현·독립 검증·PR 준비 |

세 상태 라벨 중 정확히 하나를 사용한다. `bug`, `documentation` 등 다른 용도 라벨은 함께 사용해도 된다.
라벨 누락·복수 상태·승인 불일치이면 제품 구현을 시작하지 않는다.
라벨 자체는 Human 승인 근거가 아니다. 승인 메시지·설계 버전·범위를 Issue에 기록한다.
GitHub Issue의 open/closed 상태와 구분하며 완료는 PR merged와 Issue closed로 확인한다.
Done/In Progress/In Review 상태 라벨은 추가하지 않는다. 닫힌 Issue는 마지막 상태 라벨을 유지한다.

## 실제 설정

아래 명령은 저장소 Issue/라벨 수정 권한이 있는 계정으로 실행한다.
토큰이나 인증 값을 저장소·문서·채팅에 복사하지 않는다. 기존 라벨을 먼저 확인하고
없는 라벨만 생성한다. 기존 항목을 의미 확인 없이 일괄 Ready로 옮기지 않는다.

```bash
gh label list --repo msaltnet/my-nanobot-rpi --limit 100 --json name,description
gh label create Open --repo msaltnet/my-nanobot-rpi --color 0E8A16 --description '문제 기록·초기 조사; 구현 승인 아님'
gh label create Planning --repo msaltnet/my-nanobot-rpi --color FBCA04 --description '설계 구체화·Human 승인 대기'
gh label create 'Ready for Implementation' --repo msaltnet/my-nanobot-rpi --color 1D76DB --description 'Issue 본문 설계의 Human 승인 완료'
```

템플릿 신규 생성 기본값은 Open 템플릿 `Open`, Planning 템플릿 `Planning`이다.
템플릿을 기본 브랜치에 반영하기 전에는 GitHub 신규 생성 화면에 적용되지 않을 수 있다.
CLI 신규 Issue 생성은 `--label Open` 또는 `--label Planning`을 명시한다.
기존 Issue 본문 갱신은 템플릿 frontmatter를 바꾸는 것만으로 라벨이 변경되지 않는다.

## 전환과 승인

실제 Issue 번호로 `123`을 바꾼다. 먼저 현재 라벨과 본문·승인·열린 PR을 확인한다.
아래 전환 예시는 현재 상태가 각각 Open 또는 Planning이고 상태 라벨이 하나인 경우다.

```bash
gh issue view 123 --repo msaltnet/my-nanobot-rpi --json number,state,body,labels
gh issue edit 123 --repo msaltnet/my-nanobot-rpi --remove-label Open --add-label Planning
```

Human이 현재 Issue 본문 설계를 승인하고 Ready 전환을 지시한 경우에만:

```bash
gh issue edit 123 --repo msaltnet/my-nanobot-rpi --remove-label Planning --add-label 'Ready for Implementation'
gh issue view 123 --repo msaltnet/my-nanobot-rpi --json number,state,labels
```

전환 후 상태 라벨이 하나인지 확인한다. 변경 실패나 다중 라벨이면 구현을 시작하지 않는다.
Human 직접 채팅 승인은 실제 메시지를 근거로 Issue에 기록하고 Agent 승인으로 대신하지 않는다.
설계 변경은 Ready 라벨을 제거하고 Planning으로 이동해 본문 수정·Human 재승인을 거친다.
구현 수정은 Ready를 유지하고 기존 PR에서 재테스트·재리뷰한다.
Ready 자동 전환·자동 Merge·자동 배포는 설치하지 않는다.

## 조회

```bash
# 구현 후보: 조회 결과마다 본문 설계·승인과 상태 라벨 단일성을 다시 확인한다.
gh issue list --repo msaltnet/my-nanobot-rpi --state open --label 'Ready for Implementation' --json number,title,labels
# 설계 검토 대기
gh issue list --repo msaltnet/my-nanobot-rpi --state open --label Planning --json number,title,labels
# 완료 이력: 별도 Done 라벨 없이 Issue closed 사용
gh issue list --repo msaltnet/my-nanobot-rpi --state closed --json number,title,state
```

Ready 조회 결과가 비어 있으면 현재 구현할 승인 큐가 없는 것이다. Agent가 임의 승인을 만들지 않는다.
조회는 필터 결과일 뿐 여러 상태 라벨·오래된 승인 등이 없는지 별도로 확인해야 한다.

## 운영 기록과 강제 범위

2026-10-05 세 상태 라벨 생성과 Issue #2의 Planning 라벨을 실제 확인했다.
Ready 전환은 보류했으며 실제 승인 큐 조회 결과는 비어 있었다.
Issue #1은 이번 작업의 전환 대상이 아니며 승인·상태를 추정해 변경하지 않았다.

문서와 라벨은 운영 계약이며 Git push/Merge의 서버 측 차단 장치는 아니다.
기존 테스트 CI를 유지한다. branch protection/ruleset·예약 실행을 새로 적용했다고 보고하지 않는다.
Human/Agent가 같은 GitHub 계정이면 본인 PR Approve 제약을 우회하거나 충족했다고 표시하지 않는다.
Human PR 검토·실사용 수용·명시적 Merge 승인과 현재 SHA의 검증 근거를 별도로 확인한다.
