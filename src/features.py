"""Единый контракт признаков обучения и инференса."""

import pandas as pd

FEATURES = ["views", "purchases", "ctr", "hour", "weekday", "categoryid", "available"]
SCHEMA_VERSION = "1"


def feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[:, FEATURES].astype("float64")
