import pytest

from app.persistence.structured_fragments import (
    MAX_STRUCTURED_FRAGMENTS,
    build_structured_fragments,
)


def test_single_and_grouped_attribute_are_independent_facts():
    fragments = build_structured_fragments(
        {
            "strength_class": "C30/37",
            "exposure_class": {"xc": "XC3", "xa": "XA2"},
            "concrete_type": "Normalbeton",
        }
    )
    assert fragments == [
        {"fragment": {"strength_class": "C30/37"}, "weight": 10},
        {"fragment": {"exposure_class": {"xc": "XC3"}}, "weight": 3},
        {"fragment": {"exposure_class": {"xa": "XA2"}}, "weight": 3},
        {"fragment": {"concrete_type": "Normalbeton"}, "weight": 1},
    ]


def test_multiple_attributes_match_individual_array_elements():
    assert build_structured_fragments(
        {"special_properties": ("Sichtbeton", "Pumpbeton")}
    ) == [
        {"fragment": {"special_properties": ["Sichtbeton"]}, "weight": 1},
        {"fragment": {"special_properties": ["Pumpbeton"]}, "weight": 1},
    ]


def test_numeric_and_application_values_are_preserved():
    result = build_structured_fragments(
        {"max_aggregate_size": 16, "water_cement_ratio": 0.45,
         "applications": ["Sauberkeitsschicht"]}
    )
    assert result == [
        {"fragment": {"max_aggregate_size": 16}, "weight": 1},
        {"fragment": {"water_cement_ratio": 0.45}, "weight": 1},
        {"fragment": {"applications": ["Sauberkeitsschicht"]}, "weight": 1},
    ]


def test_empty_values_and_nested_unsupported_structures_are_skipped():
    assert build_structured_fragments(
        {"exposure_class": {}, "special_properties": [], "nested": {"a": []}}
    ) == []


def test_query_is_bounded_instead_of_silently_truncated():
    with pytest.raises(ValueError, match="Too many"):
        build_structured_fragments(
            {"applications": [str(i) for i in range(MAX_STRUCTURED_FRAGMENTS + 1)]}
        )
