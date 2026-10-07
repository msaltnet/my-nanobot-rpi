# R0 검증 이력

보고서는 검증한 SHA에 대한 기록이며 이후 수정에 그대로 적용하지 않는다.

- [최초 공통 운영 문서](2026-10-05-r0-initial.md): `3f75fb5`의 문서 Test/Review PASS, 실제 운영 AC BLOCKED.
- [보드 없는 상태 관리](2026-10-05-r0-boardless.md): `1d6c5f7`의 문서 Test/Review PASS, 당시 Ready 전환 보류.

이후 [Human Ready 승인](https://github.com/msaltnet/my-nanobot-rpi/issues/2#issuecomment-5995427906)을 기록하고
Issue #2의 유일한 상태 라벨을 Ready for Implementation으로 적용했다.
`.env` 대상 항목·최신 문서 보완의 검증은 수정된 후보 SHA에서 다시 수행해 PR에 기록한다.
위 보고서 작성 당시 실제 RPi/OCI 설치·백업·복구·배포·Telegram/API 검증은 BLOCKED였다.

- [OCI 운영 데이터 백업·격리 복구](2026-10-06-oci-backup-restore.md): [Issue #4](https://github.com/msaltnet/my-nanobot-rpi/issues/4)의 승인 범위에서 OCI 실제 운영 데이터를 정지 백업하고 격리 복구·원래 서비스 상태 재개를 확인했다. 현재 문서 SHA의 독립 Tests / Agent Review는 연결 PR에 기록한다. RPi·후보 배포·운영 DB 덮어쓰기 복원·수동 외부 발송은 미수행이다.

- [OCI 최신 백업·격리 복귀·합성 tracking](2026-10-07-oci-isolated-rollback.md): [Issue #6](https://github.com/msaltnet/my-nanobot-rpi/issues/6)의 승인된 OCI 부분 범위에서 최신 백업·같은 격리 사본의 변경→복귀·39.704초 원래 운영 재개 및 외부 통신 없는 합성 기록을 검증했다. 전체 #6은 실제 수신·RPi·운영 관찰·Human 수용이 남아 BLOCKED다. 최종 문서 SHA의 독립 검증은 Issue/PR 기록을 따른다.
