import pytest

from remind_mfa.common.scenarios import ScenarioReader


@pytest.mark.parametrize(
    "value, expected",
    [
        (
            "{year: 2030, type: target}",
            {"year": 2030, "type": "target"},
        ),
        (
            "{Region: [IND, LAM, OAS, SSA], Stock Type: Res, Function: RS}",
            {"Region": ["IND", "LAM", "OAS", "SSA"], "Stock Type": "Res", "Function": "RS"},
        ),
        (
            "{Region: SSA, Function: [RS, RM, Com], Structure: M}",
            {"Region": "SSA", "Function": ["RS", "RM", "Com"], "Structure": "M"},
        ),
    ],
)
def test_parse_dict_column_uses_yaml(value, expected):
    assert ScenarioReader._parse_dict_column(value) == expected


def test_parse_dict_column_rejects_non_mappings():
    with pytest.raises(ValueError, match="Could not parse YAML dict column"):
        ScenarioReader._parse_dict_column("{[1, 2, 3]}")
