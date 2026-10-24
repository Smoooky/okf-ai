from billing import ride_price


def test_ride_price_includes_unlock_fee():
    assert ride_price(10) == 50 + 8 * 10


def test_ride_price_charges_at_least_one_minute():
    assert ride_price(0) == 50 + 8
