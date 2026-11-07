"""Interactive-card payloads for ASI:One plus a markdown fallback. Isolated here because the card
wire format must be confirmed against ASI1 docs (see OPEN_QUESTIONS.md)."""
from sharley.gate.report import render
from sharley.schemas import Spec, Verdict


def requirements_card(spec: Spec) -> dict:
    return {
        "type": "sharley.requirements",
        "title": f"{len(spec.requirements)} requirements, coverage {spec.coverage_pct}%",
        "items": [{"id": r.id, "text": r.text, "category": r.category, "evidence": r.evidence.kind,
                   "detail": r.evidence.source_span or spec.assumptions.get(r.evidence.assumption_id or "", "")}
                  for r in spec.requirements],
        "actions": [{"label": "Approve and generate tests", "reply": "approve"}],
    }


def verdict_card(v: Verdict) -> dict:
    return {
        "type": "sharley.verdict",
        "status": v.status,
        "headline": v.summary(),
        "examples": f"{v.example_passed}/{v.example_total}",
        "sealed_total": v.total_sealed,
        "models": {"implementer": v.implementer.family, "verifier": v.verifier.family},
        "requirement_ids": v.requirement_ids,
    }


def card_text(card: dict) -> str:
    """Markdown rendering so plain chat clients show the same information."""
    if card["type"] == "sharley.requirements":
        lines = [f"**{card['title']}**"]
        lines += [f"- **{i['id']}** ({i['category']}, {i['evidence']}): {i['text']}" for i in card["items"]]
        lines.append("\nReply `approve` to generate tests, or paste a corrected spec.")
        return "\n".join(lines)
    return f"**{card['status']}**\n{card['headline']}\nExamples: {card['examples']} | sealed tests: {card['sealed_total']}\n" \
           f"Implementer: {card['models']['implementer']} | Verifier: {card['models']['verifier']}"


def render_verdict_text(v: Verdict) -> str:
    return render(v)
