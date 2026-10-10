# R0 검증 이력

보고서는 검증한 SHA에 대한 기록이며 이후 수정에 그대로 적용하지 않는다.

- [최초 공통 운영 문서](2026-10-05-r0-initial.md): `3f75fb5`의 문서 Test/Review PASS, 실제 운영 AC BLOCKED.
- [보드 없는 상태 관리](2026-10-05-r0-boardless.md): `1d6c5f7`의 문서 Test/Review PASS, 당시 Ready 전환 보류.

이후 [Human Ready 승인](https://github.com/msaltnet/my-nanobot-rpi/issues/2#issuecomment-5995427906)을 기록하고
Issue #2의 유일한 상태 라벨을 Ready for Implementation으로 적용했다.
`.env` 대상 항목·최신 문서 보완의 검증은 수정된 후보 SHA에서 다시 수행해 PR에 기록한다.
위 보고서 작성 당시 실제 RPi/OCI 설치·백업·복구·배포·Telegram/API 검증은 BLOCKED였다.

- [OCI 운영 데이터 백업·격리 복구](2026-10-06-oci-backup-restore.md): [Issue #4](https://github.com/msaltnet/my-nanobot-rpi/issues/4)의 승인 범위에서 OCI 실제 운영 데이터를 정지 백업하고 격리 복구·원래 서비스 상태 재개를 확인했다. 현재 문서 SHA의 독립 Tests / Agent Review는 연결 PR에 기록한다. RPi·후보 배포·운영 DB 덮어쓰기 복원·수동 외부 발송은 미수행이다.

- [OCI 최신 백업·격리 복귀·합성 tracking](2026-10-07-oci-isolated-rollback.md): [Issue #6](https://github.com/msaltnet/my-nanobot-rpi/issues/6)의 승인된 OCI 부분 범위에서 최신 백업·같은 격리 사본의 변경→복귀·39.704초 원래 운영 재개 및 외부 통신 없는 합성 기록을 검증했다. 실제 수신·RPi·운영 관찰은 당시 미검증이다. 이후 Human이 부분 결과를 수용하고 #6을 관리상 종료했다. 이번 PR은 보고서 보존 범위이며 전체 AC PASS를 뜻하지 않는다. 최종 문서 SHA의 독립 검증과 병합 승인은 PR 기록을 따른다.

- [뉴스 오프라인 검증](2026-10-08-news-validation.md): [Issue #7](https://github.com/msaltnet/my-nanobot-rpi/issues/7)의 승인된 v1 범위에서 SQLite/합성 데이터 및 fake 수집·LLM·전송 경계를 검증했다. 테스트 SHA `d784c80`, 전체 회귀 200 passed. 실제 예약 수신·운영 관찰·정책 수용은 BLOCKED이며 #13/#14 수정은 별도 승인 대상이다. 최종 후보의 독립 Tests / Agent Review는 연결 PR에 기록한다.
- [뉴스 운영 검증 준비](2026-10-09-issue-7-news-operations-preparation.md): #7 승인 v2 실행 체크리스트·21slot 양식 준비. 실제 배포/실수신/7일 관찰은 BLOCKED이며 후보 PR 검수 후 별도 실행 승인 필요.

- [뉴스 후보 운영 사전 검증](2026-10-09-news-operations-preflight.md): 실제 DB 읽기 사본의 보존·migration·구코드 호환·격리 복구. 당시 비용 enforcement BLOCKED는 2026-10-10 Human 보류 결정으로 선행 조건에서 제외. 최신 후보 검수·별도 실행 승인·실수신 관찰은 필요하다.

- [생활 기록 오프라인 검증](2026-10-09-tracking-validation.md): Issue #8 승인 v1의 합성 SQLite/fake 경계, 신규 23개 및 전체 223개 구현자 검증. 실제 대화·수신·후속 수정·운영 관찰은 미완료. 최종 후보의 독립 Tests/Review와 결함 Issue 연결은 PR에 기록한다.

- [뉴스 최신 main 통합 검증 준비](2026-10-10-news-integration-preparation.md): 제품4cacca2 전체344/ownership43 독립 Tests 및 독립 Review PASS, 비용 보류 결정 정합화. 실제 운영/실수신·Human 수용은 미실행.
