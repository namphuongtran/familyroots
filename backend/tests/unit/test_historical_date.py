"""Unit tests for the HistoricalDate schema and to_historical_date serializer."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.historical_date import HistoricalDate, to_historical_date


@pytest.mark.unit
def test_to_historical_date_with_circa_display_and_lunar() -> None:
    result = to_historical_date(date(1750, 1, 1), "circa", "khoảng 1750", "Canh Ngọ")

    assert result == HistoricalDate(
        date=date(1750, 1, 1),
        precision="circa",
        display="khoảng 1750",
        lunar="Canh Ngọ",
    )


@pytest.mark.unit
def test_to_historical_date_with_all_none_defaults_precision_to_exact() -> None:
    result = to_historical_date(None, None, None, None)

    assert result == HistoricalDate(date=None, precision="exact", display=None, lunar=None)
    assert result.model_dump() == {
        "date": None,
        "precision": "exact",
        "display": None,
        "lunar": None,
    }


@pytest.mark.unit
def test_historical_date_precision_pattern_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        HistoricalDate(precision="bogus")
