## v4.4 성과 검증

GitHub Actions의 **Editorial performance review v4.4**를 수동 실행합니다. 기존 일정은 변경하지 않습니다. `BLOG_CONTENT`의 `상태=PUBLISHED`, `실제 발행일`과 `BLOG_ANALYTICS`의 `콘텐츠` 관계·`측정일`·누적 `조회수`를 입력한 경우에만 성과 비교에 포함합니다. 발행 후 7일 경과한 콘텐츠 중 최초 7일 이내의 최신 측정치를 사용하며, 5건 미만이면 상관 분석을 보류합니다. 실행 결과는 GitHub Actions Artifacts의 `editorial-performance-v4.4`에서 CSV/JSON으로 확인합니다. 분석은 읽기 전용이며 자동 가중치 조정·자동 발행은 하지 않습니다.

---

## v4.3.1 — 기존 추천 점수 소급 재평가

GitHub Actions → **Historical recommendation score backfill v4.3.1** → Run workflow.

- `backfill_date`: 재평가 대상 추천일(한국시간), 예: `2026-11-03`
- `dry_run=true`: 점수 미리보기만 실행, Notion 수정 없음 (기본값)
- `dry_run=false`: 추천 점수가 비어 있는 행만 업데이트
- `force=false`: 기존 점수·기존 재평가 메모가 있으면 건너뜀 (기본값)

**변경되는 필드는 오직 `추천 점수`와 `검증 메모` 두 개**입니다. 원고, 승인 상태, 원본 링크, 관계, 날짜, 분야, 순번, 기존 메모는 보존합니다. 점수와 세부 근거를 `검증 메모`에 덧붙입니다. 메모가 길어 보존할 수 없으면 덮어쓰지 않고 오류 처리합니다.

기존 기사 발행 시각은 Notion 추천 데이터에 저장되어 있지 않아, 과거 기사 시의성은 제목/요약 문구에 근거한 추정 점수입니다. 네이버 블로그 검색 결과 수는 **월간 검색량이 아닙니다**. 소급 재평가는 이미 선정된 소재의 점수를 계산할 뿐 추천 순서나 승인 결과를 변경하지 않습니다.

실행 전에 `dry_run=true`로 `BACKFILL_SCORE` 로그를 확인하고, 정상이라면 `dry_run=false`로 재실행하세요. 이 작업은 **수동 실행 전용**이며 기존 일일 검색·15분 집필 자동화 일정은 변경하지 않습니다.

---

# Blog-V1 v4.1 — 반자동 집필 연계

기존 v3.8 소재 수집(10:00·11:00 KST) 및 v4.0 최종 승인(상태=선택) 규칙은 유지합니다. 기존 15분 주기 GitHub Actions에 **원고 가져오기 및 규칙 기반 QA** 단계만 추가했습니다.

## 원고 등록 방법

1. Notion **BLOG_CONTENT**에서 `집필 요청 상태=PROMPT_READY`인 페이지를 엽니다.
2. 기존 집필 프롬프트를 ChatGPT 프로젝트에 복사하여 원고를 작성합니다. **GitHub가 ChatGPT 프로젝트를 자동 실행하지는 않습니다.**
3. 해당 Notion 페이지의 맨 아래 **제목 2 블록 `원고 제출`** 아래에 완성된 원고를 붙여넣습니다. 기존 POST-14~16 페이지에 이 제목이 없다면 직접 제목 2 블록으로 추가하세요. 일반 문단, 제목, 목록, 인용 블록만 지원합니다.
4. 기존 `Selected recommendation and draft import v4.1` GitHub Actions가 15분마다 원고를 검사합니다. 수동 실행은 `dry_run=true`로 미리보기 후 `false`로 실제 반영하세요.
5. 자동 QA 통과 시 `집필 요청 상태=DRAFT_IMPORTED`, 오류 시 `NEEDS_REVIEW`; 두 경우 모두 `상태=REVIEW`, `검수 승인=false`입니다. 원고 원문은 삭제하거나 덮어쓰지 않고, 맨 아래 `자동 검수 결과` 섹션을 추가합니다.

## 검사 범위

공백 제외 최소 500자, 미완성 자리표시자, 비밀키 의심 문자열을 차단합니다. 소제목, 참고 URL, 해시태그, 과장 표현은 경고합니다. **팩트체크·저작권·이미지 적합성·SEO 성과를 자동 보증하지 않습니다.** 사람이 최종 검수해야 합니다.

## 안전성과 제약

- OpenAI/Anthropic API를 사용하지 않습니다. 실제 원고 작성, 이미지 생성, 네이버 발행은 자동화 대상이 아닙니다.
- 기존 `BLOG_CONTENT` 원고·프롬프트·관계는 보존합니다. 원고 중복 가져오기를 막기 위해 `자동 검수 결과`가 있으면 건너뜁니다.
- 외부 Notion API 쓰기 통합 테스트는 아직 수행하지 않았습니다. 테스트는 모킹 기반입니다.
- 실패한 상태 업데이트와 QA 블록 추가가 분리되어 있으므로 일부 오류 발생 시 수동 복구가 필요할 수 있습니다.
- GitHub 예약 실행은 15분 정확히 보장되지 않으며 지연될 수 있습니다.

---

# Blog-V1 v3.9 — 15분마다 Notion 선택 소재 감지

## 구성
- `.github/workflows/daily-recommendations.yml`: v3.8 유지. 한국시간 매일 10:00 1차, 11:00 보완 실행 (UTC 01:00, 02:00).
- `.github/workflows/selected-to-chatgpt-prompt.yml`: 15분 간격 예약 확인. UTC 매시 03,18,33,48분. 예약 실행은 `DRY_RUN=false`, 수동 실행은 기본 `true`.
- `src/prompt_packet.py`: 선택된 모든 소재 처리, 기존 안전·출처 검증 및 중복 방지, 이미지 프롬프트 3개, Notion BLOG_CONTENT 저장. 오류 로그 개선.
- `tests/test_v39.py`: 상태·안전성·출처·실제 저장 모킹·중복 회복·DRY_RUN 테스트.

## 설치
1. ZIP 압축을 풀고 `Blog-V1` 저장소의 **동일 경로**에 업로드하여 덮어씁니다. `.github` 숨김 폴더 포함. `main` 브랜치에 커밋합니다.
2. Secrets: `NOTION_TOKEN`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 유지. OpenAI/Anthropic API 키 불필요.
3. GitHub Actions에서 `Selected recommendation to ChatGPT prompt v3.9`를 찾아 수동 `dry_run=true`로 테스트합니다.
4. Notion의 추천 행에서 세 안전성 `안전`, 근거 출처 `VERIFIED` 및 유효한 URL, 상태 `선택`으로 지정합니다. 출처는 사람이 실제 검증해야 합니다.
5. 다음 15분 예약 실행에서 `SELECTED_SCAN`, `PROMPT_READY <id>`, `SELECTED_SCAN_COMPLETE`를 확인합니다. BLOG_CONTENT에서 `CHATGPT_PROJECT`, `PROMPT_READY`, 이미지 프롬프트 수 3을 확인합니다.
6. 다시 실행하면 이미 연결된 항목은 조회 대상에서 빠지거나 기존 콘텐츠를 찾아 `recovered` 처리하며 신규 중복 페이지를 만들지 않습니다. 단, Notion을 동시에 수정하는 외부 작업자와의 완전한 원자적 잠금은 아닙니다.

## 주의
- Notion 변경 이벤트 즉시 실행이 아니라 **15분 간격 예약 폴링**이며 GitHub 예약 실행은 지연·누락될 수 있습니다.
- 자동으로 생성되는 것은 **ChatGPT 프로젝트에 붙여넣을 집필 요청 프롬프트**입니다. 완성 원고, 실제 이미지, ChatGPT 프로젝트 새 채팅, 네이버 발행은 자동 생성되지 않습니다.
- `DRY_RUN=true`이면 실제 Notion에 쓰지 않습니다.
- Notion 데이터 소스 ID는 기존 프로젝트 값으로 설정되어 있습니다.
- 이전 v3.3 선택 워크플로와 동일 경로로 덮어써 **두 워크플로가 중복 실행되지 않도록** 합니다.
- 이 패키지의 자동 테스트는 외부 Notion/Naver API를 호출하지 않는 모킹 기반입니다. 실제 API 통합 및 예약 실행은 GitHub 반영 후 확인해야 합니다.
