## Related Issue

Closes #<!-- Issue 번호 -->

## Summary

<!-- 문제와 구현 결과를 먼저 설명합니다. -->

## Design

<!-- Issue의 승인된 설계를 어떻게 구현했는지, 설계 승인 근거와 버전을 기록합니다. -->

## Changes

<!-- 주요 변경, 데이터 마이그레이션, 설정·배포 영향. -->

## Tests

<!-- 검증한 커밋 SHA, Tester, 명령·결과, AC별 근거. 상세 보고서 링크도 가능합니다. -->

## Agent Review

<!-- Reviewer, 검토한 커밋 SHA, 범위, Critical/Major/Minor, PASS/FAIL/BLOCKED와 보고서 링크. -->

## Known Limitations

<!-- 남아 있는 제약·수동 검증·운영 위험. 없으면 없음. -->

## Verification

<!-- Human이 실제로 확인할 절차·기대 결과. 배포가 필요한 검증은 배포 승인과 구분합니다. -->

## Deployment / Dogfooding

<!-- PR 생성 시 계획을 기록하고 실제 수행 후 결과로 갱신합니다. 미수행은 미수행으로 적습니다. -->

- 후보 SHA / 배포 대상 / 배포 승인 근거:
- 이전 운영 SHA / 백업 / 롤백 절차:
- 서비스·smoke test 결과 / 배포 보고서:
- Human 실사용 기간 / 관찰 / 수용 결과:
- Merge 후 최종 SHA와 운영 버전 확인 계획:

<!-- 테스트 통과나 PR 생성만으로 merge하지 않습니다. Human의 PR 검토·실사용 수용·명시적 병합 승인 이후에만 merge합니다. -->

## Agent Gate

- [ ] 관련 Issue의 유일한 상태 라벨이 Ready for Implementation이며 Issue 본문 설계의 Human 승인 근거가 확인됨
- [ ] 현재 커밋 기준 Tests PASS와 Acceptance Criteria별 근거를 기록함
- [ ] 현재 커밋 기준 Agent Review PASS, 미해결 Critical/Major 없음
- [ ] 알려진 제약과 운영·마이그레이션 영향을 공개함

<!-- Human PR Review는 GitHub 리뷰 또는 명시적 Human 승인으로 따로 남깁니다. 위 체크는 Human 승인을 대체하지 않습니다. -->
