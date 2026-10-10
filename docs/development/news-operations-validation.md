# #7 뉴스 후보 운영 검증 실행 패키지
[Issue #7 승인 v2](https://github.com/msaltnet/my-nanobot-rpi/issues/7)의 실행용 체크리스트이며 아래 최신 Human 비용 결정을 반영한다. 실제 서버/토큰/수신자/경로는 [비공개 기록](private-operations-record-template.md)에만 적는다.
[공통 runbook](operations-runbook.md), [21slot 기록 양식](news-observation-record-template.md), [검증 보고서](reports/2026-10-09-issue-7-news-operations-preparation.md)를 함께 사용한다.
문서 작성 단계의 서버 접속·유료 API·운영 데이터 쓰기·Telegram 발송·배포는 없다.

## 현재 비용 결정 — 2026-10-10 KST
Human은 금액 상한을 사용자 각 API·서비스 설정에서 관리하고 앱 비용 제어와 새 횟수 제한은 추후 필요 시 검토하기로 결정했다. Issue #25 설계 v1/AC는 미승인·보류(Open)다. 앱 US$5 hard enforcement 증명과 #25 구현은 운영 검증 선행 조건에서 제외한다. PR #24의 기존 전달 안전성·호출 ceiling은 유지한다.
US$5/US$4는 운영자 비용 관리·관찰 기준이며 앱 자동 차단·절대 청구 상한 보장이 아니다. 예산 확대·유료 실행 승인이 아니다. 고정 후보 검수·대상/작업창·백업/rollback·호출/발송 범위의 별도 실행 승인, smoke/7일21회 관찰·Human 수용·명시적 병합 승인 Gate는 유지한다. [현재 Issue 결정](https://github.com/msaltnet/my-nanobot-rpi/issues/7)이 과거 비용 차단 필수 문구보다 우선한다.
## 운영자가 PR 실행 승인 전에 채울 패키지
1. #14/#13 현재 후보 PR·통합 candidate SHA/gitlink와 독립 Test/Review·CI를 연결한다.
2. 이전 운영 SHA/대상/수신자/작업창/원래 unit 상태와 모든 writer·cron을 비공개로 확인한다.
3. latest consistent backup·격리 migration/restore·구코드 호환과 현재 DB 유지 rollback 근거를 연결한다.
4. 공급자 설정·사용량 확인 방법·운영자 비용 관찰/중단 담당과 US$5/US$4 기준을 기록한다. 앱 hard guard/비용 reservation 증명과 #25 구현은 선행 조건이 아니다.
5. 별도 Human 실행 승인 이후만 아래 절차의 후보 배포·smoke·관찰을 수행한다.

## 승인 계약에 따른 상세 체크리스트
## 잔여 운영 검증 계획 v2 — 2026-10-09 KST / Human 설계·AC 승인 완료

### 승인과 실행 경계
2026-10-09 KST Human이 현재 본문의 #7 v2 설계와 Acceptance Criteria를 직접 채팅으로 승인했다. **현재 상태: Ready for Implementation**; 유일한 상태 라벨은 `Ready for Implementation`이다.
승인 범위는 본문의 설계·AC에 따른 구현/테스트·독립 검수·후보 PR 준비다. 정책과 운영 수치/한도는 승인된 계획 기준으로 채택한다. 실제 운영 배포·발송은 **후보 PR 검수 후 별도 Human 승인**을 받으며, 유료 운영 호출·운영 DB/설정 쓰기·서비스 변경도 해당 구체 실행 승인 전에는 수행하지 않는다. 운영 DB 덮어쓰기 복원과 최종 병합의 별도 승인 Gate도 유지한다.
설계 승인/Ready 전환이 Tests PASS·Agent Review PASS·운영 검증 완료를 의미하지 않는다. 후보 SHA·작업창·대상·비용 상한/중단·rollback 조건은 본문의 PR Gate에서 구체화한다.

### Human 설계 승인 기록 — 2026-10-09 KST
- 근거: 이 채팅의 Human 직접 메시지:
> #13 v1, #14 v1, #7 v2 본문의 설계와 AC를 승인한다. 운영 배포·실제 발송은 후보 PR 검수 후 별도 승인한다.
- 승인 대상: 준비한 현재 #13 v1 / #14 v1 / #7 v2 각 본문의 설계와 AC. 이 Issue의 버전은 **#7 v2**이다. 승인 직전 본문이 준비본과 동일함을 조회 확인했다.
- 재전송 정책: 확인된 미발송만 최대 3회, 불확실·부분 발송·발송 후 저장 실패는 자동 재전송 중지와 명시적 수동 판단, legacy briefed 보존·소급 재전송 없음.
- 운영 계획 기준: 기존 OCI 대상/수신자 재확인, 연속 7일·정지 최대 20분·추가 유료 비용 전체 US$5 및 본문의 호출/발송/자원 ceiling과 차단 조건. **이 기준 승인은 실제 운영 실행 승인이 아니다.**
- 후속 순서: #14 → #13 → 현재 통합 후보의 독립 검수/PR → 별도 운영 실행 승인 → #7 관찰/최종 수용. 최종 merge는 별도 명시 승인 후다.
- 이전 “검토용·미승인”, Open/승인 대기, 정책 답변만 채택한 기록은 이번 설계 승인 전 이력이다. 아래 보존된 원문 이력의 과거 상태가 현재 승인을 대체하지 않는다.

### 현재 상태 / 기존 승인과 이번 변경
#7 승인 v1의 오프라인 산출물은 PR #15로 병합됐다. 기준 main `96f8b344519494cea5fd127dbe8818404fce3182`, 검수 후보 `4d0f01fa87cdf4ef1f75521949549e0fa149863b`. 기존 승인·Tests/Review·부분 수용·병합 근거는 아래 원문 이력에 보존한다.
**v2 초안 준비 당시에는 신규 운영 범위가 미승인이어서 Open으로 되돌렸다. 이번 Human 설계·AC 승인에 따라 현재는 Ready for Implementation이다.** 과거 v1 Ready와 이번 v2 설계 승인을 구분하며, 실제 v2 운영 실행은 후보 PR 검수 후 별도 승인한다. 기존 AC1–6과 전체 종료 기준을 축소하지 않는다.

[#13 수정 설계 v1](https://github.com/msaltnet/my-nanobot-rpi/issues/13)·[#14 수정 설계 v1](https://github.com/msaltnet/my-nanobot-rpi/issues/14)의 독립 구현/검수가 선행된다. PR #15 테스트 PASS를 수정 코드 후보 PASS로 재사용하지 않는다. #6은 [Human 관리상 종료 결정](https://github.com/msaltnet/my-nanobot-rpi/issues/6#issuecomment-6040692006)에 따라 closed이나 실제 smoke/RPi/장기 관찰은 미검증이다. 당시 OCI 백업·격리 복구 결과는 과거 근거이며 이번 최신 백업/후보 복귀 검증을 대신하지 않는다.

### 한 번에 검토할 범위
| 항목 | 권장안 | 승인/완료 경계 |
|---|---|---|
| 변경 | #14 사전 collect 제거 → #13 전달 원장/전용 tool·preview 분리 → 최종 통합 후보 운영 검증 | 각각 별도 Issue·PR·현재 SHA의 독립 검수. #7 제품 코드 수정 없음 |
| 재전송 | 확인된 미발송만 최초 포함 최대 3회; unknown 자동 재전송 0; 저장 payload만 운영자 수동 판단 | P1 “권장 정책 사용” 답변으로 검토 기준 채택. #13 전체 설계 승인은 별도 |
| 데이터 | 기존 기사·briefed·생활 기록 보존, legacy 실수신 미확인; 소급 발송 없음; 새 원장 자동 삭제 없음 | migration/rollback 합성 검증과 최신 실제 백업·격리 복구 |
| 운영 | 기존에 선택한 OCI 단일 Linux 호스트/현재 봇 대상 재대조, 연속 7일·세 예약 21회 | 대상은 비공개 확인, 후보 SHA·작업창 실행 승인은 PR 후. RPi 미검증 유지 |
| 비용 | 뉴스 유료 LLM/검색/오케스트레이션 US$5 관찰 기준, 신규 인프라 구매 0 | 사용자가 각 API·서비스 설정과 사용량을 관리; 앱 금액 자동 차단 보장 없음 |
| 발송 | 논리 전달 25회, part 100개, Telegram POST 최대 300회/전체 실행창 | 평소 목표가 아닌 ceiling. 21 정기+최대 3 smoke+명시 수동 재전송 최대 1 |
| 정지/복귀 | 계획 작업 최대 20분, 뉴스만 중지 우선·현재 DB 보존 코드 복귀 | 데이터 백업 복원은 별도 명시 승인. 실제 복귀 지연은 숨기지 않음 |

### 운영 전제 / 사전 점검 (새 배포 전에 필수)
1. 운영자가 지정한 OCI 기존 대상과 실제 checkout·서비스 사용자·DB/workspace 실체·bot 수신 chat/thread·단일 gateway·추가 scheduler/writer를 비공개 기록으로 대조한다. 과거 서버 SHA `4148191789bf7f17dafbc76f7b88ba6c7db9a730`를 현재 SHA로 가정하지 않는다. 다른 호스트/대상 변경은 새 지정·승인 필요. 특정 SSH 별칭/경로를 공통 요구사항으로 넣지 않는다.
2. #13/#14 현재 승인/유일 상태 라벨, 각각 PR 검수 결과·기준/후보/gitlink·CI Python 3.11/3.12를 확인한다. 통합 후보에서 관련 테스트/전체 회귀·schema/seed·entry point·기본 응답 중복 억제와 독립 Tester/Reviewer를 다시 확인한다. 고정 gitlink 설치 호환·Linux 아키텍처/패키지 `pip check`·tool 실제 등록을 확인한다.
3. 실제 유닛·gateway 내부 cron·tracking/watchdog timer·추가 작업의 KST 예정 시각과 OS timezone/NTP를 대조한다. 뉴스 07:00/14:00/20:00뿐 아니라 전체 job 사이 안전 작업창을 정한다. seed/maintenance/doctor는 쓰기·외부 호출을 동반하므로 읽기 점검으로 간주하지 않는다.
4. 새 백업·격리 복구 계획: 모든 writer의 정지와 이전 unit active/enabled 상태를 기록; checkout 밖 접근 제한된 위치에 설정/.env·DB/sidecar·workspace(스킬/cron/세션 포함)·unit/drop-in·이전 SHA/gitlink·복원 가능한 의존성을 일관되게 보관한다. manifest/digest·SQLite integrity와 기존 테이블별 행/키를 대조한다. 공개 결과에는 digest/행 수·SHA·시각만 남기고 실제 경로·수신자·토큰·본문은 공개하지 않는다.
5. additive migration을 최신 사본의 격리 환경에서 실행해 기존 테이블 내용 보존·initialize 반복·구코드 호환을 검사한다. 복구 사본에서 gateway/doctor/운영 credential로 발송하지 않는다. code rollback 연습과 DB backup 복구를 구분한다.
6. 계획 작업 정지 상한 **20분**, 권장 15분에 후보 작업 중단/복귀 착수. 백업·복구·설치·migration이 안전 작업창 안에 끝나지 않으면 배포를 시작/계속하지 않는다. 실제 원상복구가 20분을 넘으면 장애로 기록하고 중단을 이어가는 이유·Human 조치를 보고한다.
7. 유료 공급자별 사용량/권한·SDK retry·configured 모델/토큰/가격·뉴스와 agent 오케스트레이터 소비를 비공개 확인한다. 기존 시스템에는 전체 금액의 강제 budget guard가 있다는 근거가 없다. 구체 후보 SHA·작업창·대상·호출/발송 ceiling·rollback scope를 PR에 제시해 Human 실행 승인을 받은 뒤만 기동한다.

### 비용·발송·자원 제한
- **오프라인 설계/테스트 단계:** 운영 API/Telegram/DB 쓰기 0회. 현재 본문 작성에서 서버에 접속하거나 새 테스트/코드를 만들지 않는다.
- **관찰 전체 실행창:** 연속 7일 정상 관찰 + 최대 3회 수동 smoke + 명시 수동 재전송 최대 1회. 실패 뒤 기간을 다시 잡아도 비용/발송 누적 counter를 초기화하지 않는다. 예산 확대/표본 재시작은 Human 판단이다.
- root 뉴스 생성은 최대 **24회**(21 예약+3 smoke), 1회 collect·카테고리당 1회 summary·합계 summary 요청 **72회** 이내. 수집당 현재 설정 검색 최대 4개(Tavily 2, Brave 2), 총 **96회** 이내; 키 없는 소스는 skip이고 요청 0회. 뉴스 재전송은 새 수집/LLM 0회. 기타 RSS/official/fallback 요청은 각 설정 소스 1회/수집이고 기존 숨은 요청/중첩 fetch가 있으면 실제 경로 수를 preflight에서 대조한다. 소스 추가·독립 반복 collect를 하지 않는다.
- **US$5 권장 상한은 현재 요금/청구액의 단정이 아니다.** 모든 뉴스 유료 검색·요약·agent turn(스킬 실행/오케스트레이션 포함)의 초기 호출·retry·실패 과금을 포함한다. 요약 72회만으로 비용 한도를 충족했다고 판단하지 않는다. 기존 다른 기능의 비용은 비교용 baseline으로 분리하고 분리가 불가능하면 같은 실행창의 공유 사용량 전체를 보수적으로 상한에 넣는다.
- 운영자는 공급자별 설정과 사용량 확인 방법을 기록하고 뉴스·검색·agent/retry/실패 과금 및 공유 소비를 관찰한다. US$4에 신규 뉴스 실행을 수동 중단하는 기준과 US$5 관리 기준을 사용한다. 실제 청구·표시 지연/미확인도 기록하며 앱의 비용 예약·자동 차단을 주장하지 않는다.
- 금액 상한은 사용자가 각 API·서비스에서 관리한다. 앱 금액 guard·비용 예약 원장·fork 비용 capability·공유 대화/기록 차단·새 횟수 제한은 추가하지 않는다. 금액 hard enforcement 미입증만으로 운영 준비를 BLOCKED로 두지 않는다. 별도 유료 실행 승인 전에는 호출하지 않으며 plain도 agent/검색 비용이 있어 무료라고 표시하지 않는다.
- Telegram은 #13의 part당 3,500자/최대 4part, 25 logical/100part/300 POST 전체 ceiling. 재시도·HTTP timeout·실패 시도도 POST counter에 포함한다. 1회 생성·발송 실행 최대 5분, 외부 HTTP timeout 권장 10초. LLM SDK 자동 retry와 전용 sender 숨은 retry 없이 한도를 계산한다. 너무 긴 출력/한도 초과를 조용히 truncate하지 않고 발송 전 중단한다.
- 신규 VM/유료 모니터링/모델/소스 도입 0. 수집 병렬도를 임의 늘리지 않는다. 자원 권장 중단선: 시작 시 backup+restore 예상 용량의 2배와 **1 GiB 이상** 여유 디스크, 가용 메모리 **20% 이상**; 관찰 중 여유 디스크 **512 MiB 미만**, 가용 메모리 10% 미만이 5분 지속, OOM 또는 의도치 않은 gateway 재기동은 중지/조사. 서버 사양 때문에 충족하지 못하면 자동 완화하지 않고 운영 판단을 받는다. RPi 실제 검증은 여전히 미수행이다.

### 실행 순서 / Smoke / Dogfooding
1. **독립 검수 후 PR Gate:** 각 Issue 승인 설계 구현·Tests/Agent Review PASS 뒤 PR 최초 생성. 최종 통합 후보 SHA와 이전 운영 SHA, 실험 수신 대상(비공개), 작업창·정지 예산·운영자 비용 관리·관찰 계획·복귀 절차를 Human에게 제시한다. 이 계획 승인만으로 미정 후보 배포를 허용하지 않는다.
2. **승인 후보 배포:** 최신 일관 백업/격리 검증 → 승인 candidate/gitlink/venv·entry point/관리 스킬/설정 적용 → migration 무결성/기존 테이블 대조 → 단일 gateway 기동. 원래 비활성 timer/job을 일괄 켜지 않는다. gateway 내부 cron과 seed 동기화가 뉴스 예약을 되살릴 수 있음을 확인한다.
3. **수동 smoke 최대 3회:** 예약과 겹치지 않는 승인 시각에 Human이 현재 chat에서 해당 시각 뉴스 브리핑을 요청한다(아침/점심/저녁 각 최대 1회, 테스트 때문에 날짜 경계를 변조하지 않는다). 잘못된 시각의 slot을 임의 호출하지 않는다. 각 tool 1회·collect 경계 1회·선택 URL/본문 hash·LLM/plain·part별 API 응답/DB 최종 상태·Human 화면 실제 수신을 대조한다. 실제 failed/unknown을 고의 유발하거나 테스트 메시지를 운영 DB에 넣지 않는다. 3회는 상한이고 경로 중복이면 최소 표본을 사용한다.
4. **7일 실제 예약 관찰:** 후보/대상/설정이 고정된 7일 연속(07:00·14:00·20:00 KST 총 21예정)을 관찰한다. 관찰 시작/종료·KST/UTC를 기록하고 각 예약의 예정 → 실행 → 생성 → 발송 시도/API ACK → 원장 commit → Human 실수신을 별도 열로 남긴다. 받지 못한 메시지를 API ok로 PASS 처리하지 않는다. Human은 각 slot의 수신 여부와 중복·원문 유용성을 확인한다.
5. **재전송 표본:** 실패 주입은 offline에서만 수행. 자연 장애가 있으면 policy대로 failed/unknown으로 대조하고 Human 판단 기록. 명시 수동 재전송은 총 최대 1회·저장 snapshot/실수신 대조·중복 위험 수용 뒤만 실행한다. 장애가 없으면 실제 장애 표본은 미발생/N/A이고 합성 정책 검증 근거와 한계를 기록한다.
6. **생활 기록 회귀 관찰:** 실제 기존 기록·항목이 보존되고 tracking timer 원래 상태·DB integrity/키가 유지되는지 비공개 확인한다. 새 생활 기록 smoke 입력/삭제/dispatcher 수동 발송은 #7에 포함하지 않는다. 자연 발생 사용자 기록은 백업 이후 delta로 보존하며 테스트 표본으로 공개하지 않는다.
7. **수용/종료:** AC별 결과·알려진 제한·실제 API/발송 사용량·금액/자원·Human 내용 수용·현재 운영 SHA를 보고서와 PR에 기록한다. Human PR Review·실사용 수용·명시적 merge 승인 뒤 병합/Issue close. squash/rebase 시 candidate와 최종 코드 일치 및 필요한 재배포/최종 운영 버전을 확인한다. #6의 전체 RPi/생활 운영 검증을 완료했다고 확대하지 않는다.

### 실패·중단 / Rollback / 데이터 보존
- 즉시 뉴스 중지: duplicate 수신, unknown/불확실 상태, DB migration/integrity/보존 불일치, 잘못된 수신 대상, cost/POST/run limit 위반 또는 사용량 확인 불가, OOM/비정상 재기동. 한 소스 오류는 다른 수집 경로를 유지하되 소스별 FAIL/SKIP로 기록한다. 모든 소스 실패의 빈 DB 안내를 정상 수집 PASS로 위장하지 않는다.
- 예약 예상 시각 **10분 이내** 실제 수신을 권장 수용 기준으로 한다. 5분 실행 상한 종료 또는 미수신 시 추가 자동 전체 생성은 하지 않는다. 한 slot 미수신/중복은 통합 운영 검증 FAIL/BLOCKED로 남기고 새 Open 결함·정책 판단/후보 수정으로 연결한다.
- 뉴스 정지 수단은 운영 cron의 해당 3 job enabled=false와 진입 tool/dispatcher 실행 차단을 함께 확인한다. 재기동 seed에서 disabled 보존이 실제 작동해야 한다. 연결 문제로 선택 정지가 불가능하면 gateway와 관련 writer/timer를 승인 rollback 절차대로 정지하고 tracking 중단 영향도 보고한다. 두 번째 gateway나 동일 token 복제 환경은 켜지 않는다.
- 실패 시점 DB/workspace/원장과 시도/ACK/unknown을 비공개 별도 사본으로 보관. **현재 DB를 유지한 이전 코드/스킬/설정·의존성 복귀**를 우선한다. additive 원장 테이블을 삭제하지 않는다. 구코드 pre-send mark 결함이 복귀하므로 뉴스 정지를 유지하고, 미확정 원장과 legacy 상태를 대조한 뒤 Human이 뉴스 재개를 결정한다. tracking은 원래 승인 active/enabled 상태를 우선 복원한다.
- **운영 DB 덮어쓰기 복원은 이번 설계/후보 배포의 자동 rollback 범위에서 제외**한다. 필요하면 백업 시점 이후 신규 생활 기록/기사·이미 발송한 메시지와 잃을 범위를 구체적으로 제시해 별도 Human 명시 승인을 받는다. DB+sidecar·설정/workspace를 일관되게 복원하고 integrity/행/키·재발송 위험을 대조한다. 코드 SHA만 되돌려 migration이 취소됐다고 판단하지 않는다. 현재 DB와 backup을 자동 병합하지 않는다.
- 기존 기사·briefed·생활 기록의 삭제/소급 이관 없음. 새 delivery 원장/payload/unknown 자동 TTL 삭제 없음; 로그 30일 rotation, 새 rollback backup 최소 30일 보존을 권장하되 기존 더 긴 정책은 유지한다. 공간 부족 시 보존자료를 임의 삭제하지 않고 관찰을 중지한다.

### Acceptance Criteria 매핑 / 보고서
| 기존 AC | 이미 확보한 근거 | 잔여 v2 완료 근거 |
|---|---|---|
| AC1 | #15 오프라인 네 수집 경로/부분 실패/빈 결과 | 실제 소스별 성공·오류·SKIP와 DB 선택/저장 대조. 개별 소스 상태가 로그에서 확인 불가하면 미확인 |
| AC2 | 발행 시각·URL/DB 중복·카테고리 cap·검색/주간 요청 한계 조사 | 수정 후보에서도 보존. 검색 2020 이후 전체/무제한·전용 주간 interface 없음은 알려진 제약으로 Human 수용, 새 기간 기능은 비범위 |
| AC3 | 세 cron 설정만 PASS | 7일 21개 예정 각각 실행/생성/part ACK/원장/Human 실수신 표. 권장 허용: 예상 10분 이내 21/21 실수신, 잘못된 대상/중복 0 |
| AC4 | 기존 pre-send mark·upstream retry 한계 재현 | #13 정책/경계 테스트·Human P1·실제 성공 경로. 자연 장애 표본 없으면 live 장애 재전송 PASS 대신 N/A+합성 근거 |
| AC5 | #13/#14 Open 결함 분리 | 두 승인 설계의 최종 현재 SHA 독립 Tests/Review·후보 배포·수집 1회/전달 상태·Human 실사용 수용 |
| AC6 | v1 외부 영향 0 | 승인 대상·기간·운영자 비용 관리·발송/호출 ceiling·최신 백업/rollback·실제 usage/금액·자원·최종 제한 수용 |

7일 21/21 미달을 Agent가 허용치로 바꿔 PASS 처리하지 않는다. Human이 부분 결과/제한을 수용하면 그 기준과 남은 Open 후속 항목을 명시하고 원래 AC 결과는 보존한다.
산출물: 새 `docs/development/reports/` 운영 검증 보고서·색인, 비공개 실행 기록, 필요한 최소 runbook의 사실 정정. 제품 코드/새 자동화/예약 runner 구현은 #7 범위 밖이다. Issue별 격리 `codex/issue-7-news-operations-validation` 또는 동일 Issue 열린 후속 PR을 재사용한다. #15는 merged라 재사용하지 않는다.
[검증 보고서 템플릿](https://github.com/msaltnet/my-nanobot-rpi/blob/main/docs/development/verification-report-template.md)에 SHA/gitlink·OS/Python·명령/exit·AC 결과·별도 Tester/Reviewer를 적는다. 수정 후보의 뉴스/저장소/CLI 관련 검증 → `python -m pytest tests/msalt/ -q`, CI와 Linux 환경 검증. 문서 결과의 독립 검수와 운영 증거 검수를 구분하고 미수행은 BLOCKED로 남긴다.

### Human 판단 두 묶음 / 승인 기록
- **P1 제품 재전송 정책:** 2026-10-09 KST Human이 “권장 정책 사용”으로 검토 기준 채택. 확인된 미발송 최대 3회·unknown 자동 중지/수동 판단·legacy 보존/소급 재전송 없음. 당시에는 정책 기준 선택만 있었으며, 이번 후속 Human 메시지로 #13 v1 전체 설계·AC 승인이 확보됐다.
- **O1 운영 기준:** 기존 OCI 대상·현재 수신자를 실행 직전 재확인, 연속 7일·정지 최대 20분·추가 유료 비용 전체 US$5를 권장안으로 제시했다. 이번 #7 v2 본문 설계·AC 승인으로 위 운영 계획 기준을 채택했다. 실제 후보 배포·발송은 후보 PR 검수 후 별도 승인한다.
- 나머지 기술·보존·테스트·ceiling·roll back 방식은 위 권장안으로 전체 검토한다. 이번 설계 승인으로 **#13 v1 / #14 v1 / #7 v2**의 승인 범위·조건을 각 본문에 기록했다. 운영 실행·병합은 각각 이후의 concrete PR Gate다.



## 실행 결과 판정 규칙
- 실제 #13/#14 CLI/tool 이름과 동작은 최종 후보에서 대조한다. command 검증 전 운영에서 임의 실행하지 않는다.
- 정상 수신/21slot·live 오류 재전송의 미관찰은 BLOCKED/N/A로 분리한다. 코드와 문서의 준비 PASS는 전체 운영 AC PASS가 아니다.
- 후보 배포/발송 승인 이후 변경된 후보는 재검수·재승인을 받는다. Human PR Review·실사용 수용·명시 merge 전 병합하지 않는다.
