from __future__ import annotations

from evaluation.canonical_verify import expected_m5_evaluation_hash


def test_canonical_verifier_binds_to_accepted_m5_evaluation_identity() -> None:
    assert expected_m5_evaluation_hash() == "78f7e90d37fa144ea8e29fb5977c21f300f1dc7bd062969b1bb0ec4dbe96a005"
