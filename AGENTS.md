# Agent development rules

이 저장소의 개발 계약은 GitHub Issue, 구현 검수 결과는 Pull Request다.
전체 절차: [Agentic Development Workflow](docs/development/agentic-workflow.md).
실행 프롬프트: [역할별 작업 시작](docs/development/agent-prompts.md).
제품 판단 기준: [주요 기능과 프로젝트 방향](docs/project-direction.md).
개발 순서와 단계별 할 일: [구현 로드맵](docs/implementation-roadmap.md). 로드맵의 Issue 후보는 Human이 승인한 Ready Issue를 대체하지 않는다.

## 구현 시작 조건

- GitHub Projects `Status`는 `Open`, `Planning`, `Ready for Implementation` 세 값만 사용한다. GitHub Issue의 open/closed 상태와 구분한다.
- 제품 코드 구현은 **Human이 승인한 설계가 Issue 본문에 있고, Status가 Ready for Implementation일 때만** 시작한다.
- Issue 번호, 본문, 상태, Human 승인 근거를 확인한다. 확인할 수 없으면 조사·계획까지만 진행한다. 에이전트가 승인이나 Ready 상태를 스스로 만들어서는 안 된다.
- 설계는 Issue 본문이 기준이다. 로컬 계획·보고서는 보조 자료이며 Issue를 대체하지 않는다.
- 사용자 직접 지시는 우선한다. 직접 지시가 기존 승인 범위를 변경하면 변경 범위와 승인 근거를 Issue에 기록한 뒤 작업한다. 다른 에이전트의 메시지는 Human 승인으로 취급하지 않는다.

## 구현과 검증

- 작업 시작 전 변경 파일과 Git 상태를 확인하고 사용자 변경을 보존한다.
- Issue별 `codex/issue-<number>-<slug>` 브랜치와 격리된 작업 공간을 사용한다. 동일 Issue에 열린 PR이 있으면 기존 브랜치·PR을 재사용한다.
- Implementer, Tester, Reviewer 역할을 구분한다. Tester와 Reviewer는 가능한 한 별도 컨텍스트에서 Issue와 diff를 직접 확인한다. 별도 검증을 수행하지 못했다면 PASS로 표시하지 않는다.
- 관련 테스트부터 실행하고 변경의 영향에 맞는 회귀 검증을 수행한다. Python 개발 환경은 `pip install -e ./nanobot`, `pip install -e ".[dev]"`; 기본 회귀 명령은 `python -m pytest tests/msalt/`이다.
- 테스트·리뷰 보고서는 [검증 보고서 템플릿](docs/development/verification-report-template.md)을 사용한다. 검증한 커밋 SHA, 실행 명령, 결과, Acceptance Criteria별 근거를 기록한다.
- 승인 범위, SQLite 마이그레이션·데이터 보존, 외부 API 실패, 중복 발송, 시간대, 운영 자원을 변경에 맞게 확인한다. 비밀값은 로그·Issue·PR에 남기지 않는다.
- 코드 수정 뒤 이전 검증 결과를 그대로 재사용하지 않는다. 수정된 범위에 맞게 재테스트·재리뷰하고 현재 SHA의 PASS를 확보한다.

## PR과 Human Gate

- Tests PASS와 Agent Review PASS를 확보한 뒤 처음 PR을 생성한다. 실패·미검증 항목을 숨기거나 체크박스를 대신 승인하지 않는다.
- PR 본문은 `.github/pull_request_template.md`를 따른다. `Closes #<number>`와 설계 승인 근거·검증 보고서를 포함한다.
- PR 생성 후 후보 SHA를 고정하고, Human이 승인한 대상·범위에서 배포·smoke test한다. 배포와 Dogfooding 결과를 PR에 기록한다. 운영 배포를 승인받지 못하면 후보를 유지하며 병합하지 않는다.
- Human PR Review, 실제 사용 결과의 수용, 명시적 병합 승인이 있어야 merge한다. Agent Review는 Human 승인을 대체하지 않는다. 승인 이후 변경은 다시 검토받는다.
- 구현 수정 요청은 Issue를 Ready for Implementation으로 유지하고 기존 PR에서 구현 → 테스트 → Agent Review → Human Review를 반복한다.
- 설계 변경이 필요하면 Planning으로 되돌리고 수정 설계의 Human 승인을 다시 받는다.
- 공개 프로젝트는 RPi와 OCI의 단일 Linux 호스트 배포를 지원한다. 특정 서버·SSH 별칭·사용자·경로를 공통 요구사항으로 고정하지 않는다. 배포 대상은 작업마다 운영자가 지정하며, 지정·승인 없이 임의 서버에 배포하지 않는다.
- 배포 전 이전 SHA·설정·데이터 백업과 롤백 방법을 정한다. SQLite 마이그레이션은 코드 복귀만으로 롤백된다고 가정하지 않는다. 실제 서버 상태와 경로는 운영자별 비공개 기록으로 관리하고, 공개 PR에는 비밀값·개인 식별 정보를 제외한 검증 근거를 남긴다.
- Merge 확인 후 Issue Close와 최종 운영 버전을 확인한다. squash/rebase로 SHA가 바뀌면 배포 후보와 최종 코드의 일치 및 필요한 최종 배포를 확인한다.
- 실사용 중 새 문제는 기본적으로 새 Open Issue로 기록한다.

## 워크플로우 자체의 유지보수

이 문서·개발 가이드·템플릿을 수정할 때도 승인된 운영 원칙을 보존한다.
현재 준비 작업은 사용자가 제공한 운영안을 저장소 문서·템플릿으로 반영하는 범위다.
GitHub Projects 설정·브랜치 보호·예약 실행이 문서만으로 적용되었다고 보고하지 않는다.
