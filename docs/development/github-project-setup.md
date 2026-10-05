# GitHub Projects 연결

대상 저장소: `msaltnet/my-nanobot-rpi`. 개발 규칙은 [워크플로우](agentic-workflow.md)를 따른다.
Projects의 단일 선택 `Status`를 상태의 기준으로 사용하며 상태 라벨을 별도로 만들지 않는다.

## 적용 범위

이 설정은 프로젝트 개발·기여를 위한 보드 운영 절차다. RPi/OCI에 앱을 설치하는 사용자가
Projects 보드를 만들거나 유지관리자의 GitHub 인증·서버에 접근할 필요는 없다.
실제 보드 URL·권한·적용 상태는 보드를 운영하는 사람이 확인한다. 문서가 있다고 설정이 적용된 것은 아니다.

## 권한과 대상 확인

기존 보드를 사용한다면 URL을 확인하고, 없다면 개인 소유의 `my-nanobot-rpi Development` 보드를 만든다.
사용자가 CLI 권한 확장을 선택한 경우 다음 명령의 GitHub 인증 절차를 직접 완료한다.

```bash
gh auth refresh -h github.com -s project
gh project list --owner msaltnet --format json
```

인증 후 기존 보드를 확인해 중복 생성하지 않는다. UI에서도 보드와 필드를 구성할 수 있다.
조회만 필요하면 `read:project`, 생성·수정은 `project` 권한이 필요하다.
인증 토큰을 저장소·문서·채팅에 복사하지 않는다.
CLI 참고: [Projects 명령](https://cli.github.com/manual/gh_project), [인증 권한 갱신](https://cli.github.com/manual/gh_auth_refresh).

## 보드 구성 체크리스트

- [ ] 보드 URL을 정하고 이 문서에 기록한다.
- [ ] 저장소 `msaltnet/my-nanobot-rpi`를 보드에 연결한다.
- [ ] 기존 `Status` 필드의 선택지를 `Open`, `Planning`, `Ready for Implementation` 세 값으로 설정한다.
- [ ] 기본 `Todo`, `In Progress`, `Done`을 그대로 병행하지 않는다. 기존 값이 있다면 진행 항목의 의미를 확인하고 옮긴 뒤 정리한다.
- [ ] 새 Issue를 수동 추가하거나 보드의 auto-add로 추가하고 초기 Status를 Open으로 설정한다.
- [ ] 자동화에서 Issue closed / PR merged → Done 전환과 Status 변경 → Issue Close를 끈다.
- [ ] Issue closed는 GitHub 기본 상태로 유지하고, 닫힌 항목은 완료 이력으로 조회하거나 archive한다.
- [ ] Agent가 Human 승인 없이 Ready로 전환하는 자동화를 만들지 않는다.
- [ ] Board view는 Status별로 그룹화하고 `repo:msaltnet/my-nanobot-rpi is:issue is:open`을 필터로 사용한다.
- [ ] 구현 큐 view는 `repo:msaltnet/my-nanobot-rpi is:issue is:open status:"Ready for Implementation"`을 필터로 사용한다.
- [ ] 완료 view는 `repo:msaltnet/my-nanobot-rpi is:issue is:closed`로 조회한다. 새 상태를 추가하지 않는다.
- [ ] PR 검수는 저장소의 열린 PR 화면과 Issue 연결에서 확인한다. PR을 Issue 구현 큐에 섞지 않는다.

GitHub Projects 기본 자동화는 종료된 항목을 Done으로 옮길 수 있으므로 반드시 점검한다.
설정 참고: [기본 자동화](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations),
[필드](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields),
[필터](https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/filtering-projects).

## 실제 동작 점검

1. 작업용 Open Issue를 보드에 넣고 Open 단계에서 Agent가 구현하지 않는지 확인한다.
2. Planner가 본문을 채운 뒤 Planning으로 유지하는지 확인한다.
3. Human이 본문 설계를 승인하고 Ready로 변경한 뒤에만 구현을 시작한다.
4. 독립 검증과 리뷰가 PASS인 커밋으로 PR을 만들고 Issue를 연결한다.
5. 승인된 후보를 배포·실사용한 후 Human이 PR을 수용·병합한다.
6. Issue가 Closed가 되고 Status에 네 번째 값이 생기지 않는지 확인한다.

새 작업용 Issue는 실제 사용할 문제로 작성한다. 위 점검 때문에 의미 없는 제품 Issue를 자동 생성하지 않는다.

## 서버 측 강제와 운영 규칙의 차이

AGENTS.md와 템플릿은 사람이 검토할 계약을 만든다. Projects Status만으로 Git push나 Merge가 차단되지는 않는다.
저장소 ruleset·branch protection을 사용하려면 별도로 설정하고 실제 적용을 확인한다.
Human과 Agent가 같은 계정으로 PR을 만들면 자신의 PR에 Approve review를 할 수 없으므로,
형식적인 required approving review를 임의로 켜서 단독 운영을 막지 않는다.
별도 검토자 계정을 사용하는 경우에만 required review와 stale approval 해제 같은 보호 설정을 검토한다.

이번 준비에서는 서버 측 보호·Projects 토큰을 사용하는 Actions·자동 Agent dispatch·예약 실행을 설치하지 않는다.
기존 테스트 CI를 유지하며, 자동화를 추가하려면 보드·권한·실패 동작을 별도 Issue에서 설계한다.
