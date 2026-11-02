# Blog-V1 v3.4 — 외부 LLM API 없는 안전 검토 + ChatGPT 프로젝트 집필

## 운영 방식
1. `src.daily`: 네이버 뉴스 검색으로 분야별 후보 수집 → 금지어 및 공식 검증 출처 확인 → 논란도·불쾌도 **주의**, 상태 **보류**로 Notion 등록. 규칙 통과는 안전 확정이 아닙니다.
2. 사람이 Notion 일일 추천 DB에서 **출처 원문과 문맥을 검증**하고 논란도·신빙성·불쾌도를 모두 **안전**으로 변경한 뒤 상태를 **선택**으로 지정합니다.
3. `src.prompt_packet`: 승인된 후보만 BLOG_CONTENT에 **PROMPT_READY** 집필 요청을 생성합니다. 같은 소재에 연결된 기존 콘텐츠가 있으면 중복 생성하지 않습니다.
4. ChatGPT [블로그 자동화 포스팅 원고 프로젝트](https://chatgpt.com/g/g-p-6ae813d2e0148191bb77ff00d428cf9d-beulrogeu-jadonghwa-poseuting-weongo/project)에서 사람이 새 채팅을 열고 프롬프트를 복사해 원고를 작성합니다.
5. 집필 프롬프트는 통일된 파스텔 색상 계열의 **썸네일 16:9 1개 + 본문 4:3 2개** 이미지 생성 프롬프트를 포함합니다. 이미지 자체를 자동 생성하지 않습니다.

## GitHub 설정
- Secrets: `NOTION_TOKEN`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (Anthropic/OpenAI 키 불필요)
- Actions: `daily-recommendations.yml`, `selected-to-chatgpt-prompt.yml` 두 개를 수동 실행으로 테스트하세요.
- **예약 실행은 의도적으로 비활성화**했습니다. Notion 통합 테스트 후 사용자가 승인한 시점에만 schedule을 활성화하세요.
- `generate-post.yml.disabled`, `selected-to-draft.yml.disabled`는 과거 코드 참고용으로 보존되며 실행되지 않습니다.
- `DRY_RUN=true`를 우선 실행하세요. Notion 읽기 및 네이버 API 요청은 여전히 발생합니다.
- `src/main.py`의 API 집필 함수는 실행 시 오류를 내도록 비활성화했습니다. 기타 Notion/네이버 헬퍼는 유지됩니다.

## 제한
- 출처의 주장별 교차 검증은 자동 구현되지 않았습니다. Notion에서 사람이 근거를 확인해야 합니다.
- 뉴스 API 기반 수집만 구현되어 있으며 문화포털/KOPIS/정부24 직접 수집은 미구현입니다.
- Notion에서 안전 선택해도 ChatGPT 프로젝트에 새 채팅을 자동 생성할 수 없습니다.
- 저장소 Public이면 비공개 전환을 권장합니다. API 키를 코드에 포함하지 마세요.

## 테스트
`python -m pip install -r requirements.txt && python -m unittest discover -s tests -v`


## v3.5: 후보 탈락 사유 진단
- `SOURCE_DIAGNOSTICS`: 사용 가능한 VERIFIED + 원문확인 출처 수 및 공식 도메인 수
- `GATE_DIAGNOSTICS`: 분야별 A/B/A-C 탈락 집계. 개인정보 및 API 키 출력 없음.
- 마지막 JSON `summary`에도 `rejection_reasons`가 포함됩니다.
- `DRY_RUN=true` 유지. 후보별 전문이나 실제 기사 URL을 로그에 노출하지 않습니다.
- **중요:** 출처 검증이 되지 않은 자료를 VERIFIED로 변경하지 마세요.
- 실제 기사 주장과 출처의 일치 여부는 사람 검토가 필수입니다.
- 일일 추천은 0건일 수 있으며 이는 실패가 아닙니다.
- GitHub Actions는 `.github/workflows/daily-recommendations.yml`을 덮어씁니다.


## v3.6: 출처 검증 대기 큐
- 기본 `REVIEW_QUEUE=true`: 네이버 뉴스에서 분야별 최대 2건을 **검증 대기**로 선별합니다. 이는 게시 추천이나 사실 검증이 아닙니다.
- `DRY_RUN=true`에서 실제 API 읽기만 실행하며 Notion 페이지를 생성하지 않습니다.
- `DRY_RUN=false`에서 후보별 BLOG_SOURCES에 `UNVERIFIED`, `원문 확인 여부=false` 자료를 생성하고, BLOG_DAILY_RECOMMENDATIONS에 `보류` 및 A/B/C `주의`로 연결합니다.
- 사용자는 원문과 별도의 공식 근거를 검증하고 출처를 `VERIFIED`로 변경해야 합니다. 기사 원문 자체만으로 공식 근거를 충족한다고 간주하지 마세요.
- ChatGPT 프롬프트 단계는 세 가지 안전 판정 모두 `안전`, 출처 `VERIFIED` 조건을 유지합니다.
- 기존 날짜·분야에 추천 행이 있으면 중복 방지를 위해 해당 분야를 건너뜁니다. 새로운 테스트 날짜를 쓰거나 기존 데이터를 검토하세요.
- 후보 제목은 안전성 및 사실관계를 보증하지 않습니다. 규칙 기반 필터는 놓치는 위험이 있으므로 사람 검토가 필수입니다.
- `REVIEW_QUEUE=false`는 기존 v3.5 엄격한 추천 로직으로 되돌리는 선택지입니다.


## v3.7: 날짜·분야·원문 URL 중복 방지 강화
- 같은 `추천일 + 분야`에 **기존 행이 하나라도 있으면** 해당 분야 전체를 건너뜁니다. 부분 저장 후 재실행해도 기존 행을 덮어쓰지 않습니다.
- 같은 날짜의 **다른 분야**에 이미 등록된 동일 기사 URL도 후보에서 제외합니다. URL의 `utm_*`, `fbclid`, `gclid`, `ref`, `source` 추적 파라미터는 중복 판정에서 무시합니다.
- 동일 실행 내 중복 URL도 제외합니다.
- `DEDUP_DIAGNOSTICS`, `DEDUP_SKIP`, `DEDUP_FILTER` 로그를 추가했습니다.
- **안전 우선:** 부분 저장된 분야는 자동 보충하지 않습니다. Notion에서 확인한 뒤 수동으로 정리해야 합니다.
- **동시 실행:** 동일 워크플로의 GitHub Actions `concurrency`로 직렬화합니다. 다른 워크플로/외부 클라이언트의 동시 쓰기까지 데이터베이스 수준에서 원자적으로 방지하지는 못합니다.
- 예약 실행은 계속 비활성화, `dry_run=true` 기본 유지.
