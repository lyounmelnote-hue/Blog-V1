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
