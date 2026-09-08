from __future__ import annotations

import pytest

from evaluation.postgres_profile import _index_names, _percentile, _safe_benchmark_database


def test_profile_percentile_is_interpolated_and_deterministic() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert _percentile(values, 0.5) == 3.0
    assert _percentile(values, 0.95) == pytest.approx(80.8)


def test_profile_refuses_non_benchmark_database() -> None:
    with pytest.raises(SystemExit, match="bench.*test"):
        _safe_benchmark_database("postgresql://postgres:postgres@127.0.0.1:5432/fabops")


def test_profile_accepts_explicit_benchmark_database() -> None:
    assert (
        _safe_benchmark_database("postgresql://postgres:postgres@127.0.0.1:5432/fabops_bench")
        == "fabops_bench"
    )


def test_profile_collects_nested_index_names() -> None:
    plan = {
        "Node Type": "Limit",
        "Plans": [
            {
                "Node Type": "Index Scan",
                "Index Name": "fabops_event_log_event_type_sequence_idx",
            }
        ],
    }

    assert _index_names(plan) == ["fabops_event_log_event_type_sequence_idx"]
