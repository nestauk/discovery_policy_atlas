import hashlib


def stable_doc_id(
    doi: str | None,
    source_id: str | None,
    title: str | None,
    year: int | None,
) -> str:
    """Deterministic doc_id selection.

    Preference order:
    1) DOI (normalized)
    2) Source ID (string)
    3) Hash of title + year
    """

    if doi:
        return doi.strip().lower()

    if source_id:
        return str(source_id).strip()

    basis = f"{(title or '').strip()}::{year or ''}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
