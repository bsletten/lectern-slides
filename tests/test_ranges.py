"""Exhaustive grammar cases for the slide-range parser."""

import pytest

from lectern.errors import RangeError
from lectern.ranges import parse_ranges


@pytest.mark.parametrize(
    ("spec", "total", "expected"),
    [
        ("1", 5, [1]),
        ("5", 5, [5]),
        ("1-3", 5, [1, 2, 3]),
        ("1-3,14", 14, [1, 2, 3, 14]),
        ("2-2", 5, [2]),
        ("3-", 5, [3, 4, 5]),
        ("-3", 5, [1, 2, 3]),
        ("-", 4, [1, 2, 3, 4]),
        ("  1 - 3 , 5 ", 5, [1, 2, 3, 5]),  # whitespace ignored everywhere
        ("3,1", 5, [3, 1]),  # order preserved as written
        ("1-2,2-3", 5, [1, 2, 2, 3]),  # overlaps kept, not de-duped
    ],
)
def test_valid_specs(spec, total, expected):
    assert parse_ranges(spec, total) == expected


@pytest.mark.parametrize(
    ("spec", "total"),
    [
        ("", 5),
        ("   ", 5),
        ("1,,3", 5),  # empty segment
        ("0", 5),  # below lower bound
        ("6", 5),  # above upper bound
        ("4-6", 5),  # range runs past the end
        ("3-1", 5),  # reversed
        ("x", 5),  # not a number
        ("1-x", 5),  # bad endpoint
        ("1-2-3", 5),  # malformed range
    ],
)
def test_invalid_specs_raise(spec, total):
    with pytest.raises(RangeError):
        parse_ranges(spec, total)


def test_error_message_cites_count():
    with pytest.raises(RangeError, match=r"file has 3 slides"):
        parse_ranges("9", 3)

    with pytest.raises(RangeError, match=r"file has 1 slide\b"):
        parse_ranges("9", 1)
