from reputation_core.capabilities import CAPABILITY_TEMPLATES, require_capability_template
from reputation_core.claims import EXTRACTOR_VERSION, extract_claim_candidates


def test_every_initial_template_has_ten_functional_slots() -> None:
    assert set(CAPABILITY_TEMPLATES) == {"get_tx_status", "verify_record", "anchor_record"}
    assert all(template.functional_slot_count == 10 for template in CAPABILITY_TEMPLATES.values())
    assert require_capability_template("anchor_record").mode == "write"
    assert require_capability_template("verify_record").mode == "read"


def test_extracts_positive_and_negative_chinese_claims_with_exact_spans() -> None:
    document = "本服务支持查询交易状态，但不支持链上存证。"

    claims = extract_claim_candidates(document, "description")

    assert [(claim.quote, claim.polarity, claim.candidate_capability) for claim in claims] == [
        ("查询交易状态", "positive", "get_tx_status"),
        ("链上存证", "negative", "anchor_record"),
    ]
    assert all(document[claim.start : claim.end] == claim.quote for claim in claims)
    assert all(claim.extractor_version == EXTRACTOR_VERSION for claim in claims)


def test_extracts_mixed_language_and_keeps_generic_claim_unmapped() -> None:
    document = "Supports verify_record. 计划支持 anchor_record，并支持所有链上操作。"

    claims = extract_claim_candidates(document, "metadata.description")

    assert [(claim.quote, claim.polarity, claim.candidate_capability) for claim in claims] == [
        ("verify_record", "positive", "verify_record"),
        ("anchor_record", "ambiguous", "anchor_record"),
        ("支持所有链上操作", "positive", None),
    ]


def test_previous_sentence_negation_does_not_leak_to_next_claim() -> None:
    document = "不支持链上存证。支持只读核验。"

    claims = extract_claim_candidates(document, "description")

    assert [(claim.polarity, claim.candidate_capability) for claim in claims] == [
        ("negative", "anchor_record"),
        ("positive", "verify_record"),
    ]


def test_empty_document_has_no_candidates_and_field_path_is_required() -> None:
    assert extract_claim_candidates("", "description") == ()

    try:
        extract_claim_candidates("支持链上存证", "")
    except ValueError as error:
        assert str(error) == "field_path is required"
    else:
        raise AssertionError("missing field path must be rejected")
