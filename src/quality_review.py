"""v4.2 deterministic editorial quality review; never publishes or grants human approval."""
import os
import re
from . import main, draft_import

CONTENT = os.getenv("NOTION_CONTENT_DS", main.CONTENT)
DRY = lambda: os.getenv("DRY_RUN", "true").lower() == "true"
REPORT = "v4.2 품질 평가 결과"

def score_draft(draft):
    text = draft.strip()
    compact = re.sub(r"\s+", "", text)
    headings = re.findall(r"(?m)^#{1,3}\s+(.+)", text)
    urls = re.findall(r"https?://[^\s)\]>]+", text)
    hashtags = re.findall(r"(?m)(?<!\w)#[가-힣A-Za-z][가-힣A-Za-z0-9_]+", text)
    qa = draft_import.qa(text)
    checks = {
        "SEO": (10 if headings else 0) + (10 if len(headings) >= 3 else 0) + (5 if hashtags else 0),
        "출처": (10 if urls else 0) + (10 if len(set(urls)) >= 2 else 0) + (5 if not qa["errors"] else 0),
        "실용성": (10 if len(compact) >= 800 else 0) + (10 if len(headings) >= 3 else 0),
        "차별성": 0,  # Cross-document uniqueness needs separate comparison; never award unverified points.
        "이미지·가독성": (5 if headings else 0) + (5 if re.search(r"이미지|사진|삽입 위치", text) else 0),
        "안전성": 5 if not qa["errors"] and not qa["warnings"] else 0,
    }
    blockers = list(qa["errors"])
    if not urls:
        blockers.append("참고 출처 URL 없음")
    if qa["warnings"]:
        blockers.append("기존 QA 주의사항 수동 검토 필요")
    blockers.append("사실·저작권·출처 진위 및 중복성 사람 검수 필요")
    total = sum(checks.values())
    return {"score": total, "checks": checks, "blockers": blockers,
            "quality_pass": total >= 85 and not qa["errors"],
            "approval_eligible": False}

def evaluate(page):
    props = page.get("properties", {})
    status = (props.get("집필 요청 상태", {}).get("select") or {}).get("name")
    if status != "원고 등록 완료":
        return "skip"
    if (props.get("검수 승인", {}).get("checkbox") or
        (props.get("상태", {}).get("select") or {}).get("name") == "발행 완료"):
        return "skip"
    blocks = draft_import.get_blocks(page["id"])
    if any(draft_import.block_text(b).strip() == REPORT for b in blocks):
        return "already-reviewed"
    draft = draft_import.extract_draft(blocks)
    if not draft:
        return "no-draft"
    result = score_draft(draft)
    print("QUALITY_V42", page["id"], "score=", result["score"],
          "blockers=", len(result["blockers"]), "dry_run=", DRY())
    if DRY():
        return "preview"
    message = ("자동 점수: {score}/100 | 항목: {checks}\n"
               "발행 승인: 불가(사람 검수 필수)\n"
               "확인 필요: {blockers}\n"
               "자동 평가는 실제 출처 진위·저작권·중복을 확인하지 않습니다.").format(
                   score=result["score"], checks=result["checks"],
                   blockers="; ".join(result["blockers"]))
    # Append first; reruns cannot duplicate report even if page property update fails.
    main.notion("PATCH", f'/blocks/{page["id"]}/children', safe_retry=False,
                json={"children": [
                    {"object":"block","type":"heading_2","heading_2":{"rich_text":main.rich(REPORT)}},
                    {"object":"block","type":"paragraph","paragraph":{"rich_text":main.rich(message)}}]})
    main.notion("PATCH", f'/pages/{page["id"]}', json={"properties":{
        "SEO 점수":{"number":result["score"]},
        "검수 승인":{"checkbox":False},
        "검증 메모":{"rich_text":main.rich("v4.2 품질 자동 평가 완료. 사람 검수 및 발행 승인 별도 필요.")}
    }})
    return "reviewed"

def run():
    pages = main.query(CONTENT, {"property":"집필 요청 상태",
                                  "select":{"equals":"원고 등록 완료"}}, 100)
    errors = []
    for page in pages:
        try:
            print("QUALITY_RESULT", page["id"], evaluate(page))
        except Exception as exc:
            errors.append(page["id"])
            print("QUALITY_ERROR", page["id"], type(exc).__name__, str(exc))
    print("QUALITY_COMPLETE", "examined=", len(pages), "errors=", len(errors))
    if errors:
        raise RuntimeError(f"Quality review failed for {len(errors)} pages")

if __name__ == "__main__":
    run()
