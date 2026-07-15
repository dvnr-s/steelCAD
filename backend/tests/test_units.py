"""fmt_ft_in must mirror frontend lib/format.js fmtFtIn exactly."""
from app.services.units import fmt_ft_in


def test_whole_feet():
    assert fmt_ft_in(5) == "5'"
    assert fmt_ft_in(0) == "0'"


def test_feet_and_inches():
    assert fmt_ft_in(5.5) == "5'6\""
    assert fmt_ft_in(2.25) == "2'3\""
    assert fmt_ft_in(3.75) == "3'9\""


def test_sub_foot_is_inches_only():
    assert fmt_ft_in(0.75) == '9"'
    assert fmt_ft_in(0.5) == '6"'


def test_float_drift_absorbed():
    assert fmt_ft_in(4.7499999999999999) == "4'9\""
    assert fmt_ft_in(2.499999999) == "2'6\""
