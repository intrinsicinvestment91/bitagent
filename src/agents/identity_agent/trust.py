from typing import Any


def calculate_trust_score(
    paid_nip05: bool,
    active_registration: bool,
    category: str | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    score = 0.0
    basis: list[str] = []

    if paid_nip05:
        score += 0.40
        basis.append("paid_nip05")

    if active_registration:
        score += 0.25
        basis.append("active_registration")

    if category and category.strip():
        score += 0.15
        basis.append("category_present")

    tag_count = min(len(tags or []), 4)
    if tag_count > 0:
        score += tag_count * 0.05
        basis.append("tags_present")

    score = min(score, 1.0)
    return {"score": round(score, 4), "basis": basis}
