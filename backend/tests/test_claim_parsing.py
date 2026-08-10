from claim_engine import parse_structured_claim_response


def test_parses_markdown_fenced_json_response():
    raw = '''```json
{
  "decision": "approved",
  "confidence": "high",
  "rationale": "The event is covered under the policy terms.",
  "covered_items": ["hospitalisation"],
  "exclusions": [],
  "missing_information": [],
  "next_steps": ["Submit the discharge summary"]
}
```'''

    parsed = parse_structured_claim_response(raw)

    assert parsed["decision"] == "approved"
    assert parsed["confidence"] == "high"
    assert parsed["covered_items"] == ["hospitalisation"]
    assert parsed["next_steps"] == ["Submit the discharge summary"]


def test_parses_json_embedded_in_text():
    raw = '''The claim is eligible.\n```json\n{"decision": "needs_review", "confidence": "medium", "rationale": "Additional documents are required.", "covered_items": [], "exclusions": ["pre-existing condition"], "missing_information": ["doctor note"], "next_steps": ["Upload the doctor note"]}\n```'''

    parsed = parse_structured_claim_response(raw)

    assert parsed["decision"] == "needs_review"
    assert parsed["confidence"] == "medium"
    assert parsed["missing_information"] == ["doctor note"]
