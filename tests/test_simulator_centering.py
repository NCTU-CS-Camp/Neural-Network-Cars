from __future__ import annotations

from pipeline.simulator import _image_center_offsets


def test_image_center_offsets_are_balanced_when_side_clearances_match():
    center_offset, normalized = _image_center_offsets(left_clearance=50.0, right_clearance=50.0)
    assert center_offset == 0.0
    assert normalized == 0.0


def test_image_center_offsets_use_relative_side_clearance_difference():
    center_offset, normalized = _image_center_offsets(left_clearance=30.0, right_clearance=90.0)
    assert center_offset == 30.0
    assert normalized == 0.5


def test_image_center_offsets_treat_no_side_clearance_as_off_center():
    center_offset, normalized = _image_center_offsets(left_clearance=0.0, right_clearance=0.0)
    assert center_offset == 0.0
    assert normalized == 1.0
