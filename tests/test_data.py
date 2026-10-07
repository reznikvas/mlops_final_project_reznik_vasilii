"""Границы target и отсутствие размножения просмотров."""

import pandas as pd

from src.data import DAY, make_target


def test_target_nearest_future_purchase() -> None:
    views = pd.DataFrame(
        {
            "timestamp": [100, 200, 300, DAY + 1000],
            "visitorid": [1, 1, 2, 1],
            "itemid": [7, 7, 7, 7],
        }
    )
    purchases = pd.DataFrame(
        {
            "timestamp": [100, 150, 201, DAY + 300],
            "visitorid": [1, 1, 1, 2],
            "itemid": [7, 7, 7, 7],
        }
    )
    result = make_target(views, purchases)
    assert len(result) == len(views)
    assert result.target.tolist() == [1, 1, 1, 0]


def test_target_same_time_is_not_future() -> None:
    frame = pd.DataFrame({"timestamp": [100], "visitorid": [1], "itemid": [7]})
    assert make_target(frame, frame).target.tolist() == [0]


def test_equal_timestamps_have_canonical_order() -> None:
    views = pd.DataFrame(
        {"timestamp": [100, 100, 100], "visitorid": [3, 1, 2], "itemid": [7, 7, 7]}
    )
    purchases = pd.DataFrame({"timestamp": [200], "visitorid": [2], "itemid": [7]})
    first = make_target(views, purchases)
    second = make_target(views.iloc[::-1], purchases)
    pd.testing.assert_frame_equal(first, second)
    assert first.visitorid.tolist() == [1, 2, 3]
