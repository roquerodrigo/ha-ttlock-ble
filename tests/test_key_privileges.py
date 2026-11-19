from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from custom_components.ttlock_ble.key_privileges import can_manage_passage_mode

if TYPE_CHECKING:
    from ttlock_ble import VirtualKey


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, True),
        ({"adminPs": ""}, False),
        ({"userType": "110302"}, False),
        ({"featureValue": "1"}, False),
        ({"featureValue": f"{1 << 22:x}"}, True),
    ],
)
def test_passage_mode_needs_an_admin_key_on_a_lock_that_has_it(
    sample_virtual_key: VirtualKey, changes, expected
) -> None:
    for name, value in changes.items():
        setattr(sample_virtual_key, name, value)
    assert can_manage_passage_mode(sample_virtual_key) is expected
