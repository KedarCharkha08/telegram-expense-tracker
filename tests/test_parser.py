from datetime import date, timedelta

import pytest

from parser import DEFAULT_CATEGORY, ParseError, parse_expense

TODAY = date(2026, 8, 9)


def p(msg):
    return parse_expense(msg, today=TODAY)


@pytest.mark.parametrize(
    "message,amount,category",
    [
        ("250 Food Dinner", 250.0, "Food"),          # the spec format
        ("dinner 250", 250.0, "Food"),               # reversed
        ("250", 250.0, DEFAULT_CATEGORY),            # bare amount
        ("₹1,250 uber to airport", 1250.0, "Transport"),
        ("paid rs 450.50 for medicines", 450.50, "Health"),
        ("1.2k rent", 1200.0, "Rent"),
        ("2k netflix subscription", 2000.0, "Entertainment"),
        ("1,23,456 investment sip", 123456.0, "Investment"),
        ("spent 80 on chai", 80.0, "Food"),
        ("groceries 1500 dmart", 1500.0, "Groceries"),
        ("1.5 lakh flight tickets", 150000.0, "Transport"),
    ],
)
def test_amount_and_category(message, amount, category):
    e = p(message)
    assert e.amount == amount
    assert e.category == category


def test_description_strips_noise():
    e = p("paid rs 450 for uber to office")
    assert e.description == "uber office"


def test_description_empty_when_only_category_word():
    assert p("250 food").description == ""


def test_keyword_that_restates_the_category_is_dropped():
    e = p("250 food dinner")
    assert (e.category, e.description) == ("Food", "dinner")


def test_informative_keyword_survives_in_description():
    """'uber' maps to Transport but still carries information 'food' doesn't."""
    e = p("450 uber to airport")
    assert (e.category, e.description) == ("Transport", "uber airport")


def test_relative_date():
    assert p("300 lunch yesterday").spent_on == TODAY - timedelta(days=1)
    assert p("300 lunch").spent_on == TODAY


def test_raw_message_preserved():
    assert p("  250 Food Dinner  ").raw_message == "250 Food Dinner"


@pytest.mark.parametrize("message", ["", "   ", "hello there", "/start", "0 food"])
def test_rejects_messages_without_amount(message):
    with pytest.raises(ParseError):
        p(message)
