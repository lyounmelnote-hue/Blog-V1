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
