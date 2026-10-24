"""Wheelo billing: card hold at ride start, per-minute charge at ride end."""

from dataclasses import dataclass

UNLOCK_FEE_RUB = 50
PER_MINUTE_RUB = 8
HOLD_RUB = 300
MAX_CHARGE_RETRIES = 3


@dataclass
class Charge:
    ride_id: str
    amount_rub: int
    status: str  # held | charged | failed


def hold(payments, card_token: str, ride_id: str) -> Charge:
    payments.hold(card_token, HOLD_RUB, reference=ride_id)
    return Charge(ride_id, HOLD_RUB, "held")


def ride_price(minutes: int) -> int:
    return UNLOCK_FEE_RUB + PER_MINUTE_RUB * max(minutes, 1)


def charge(payments, card_token: str, ride_id: str, minutes: int) -> Charge:
    amount = ride_price(minutes)
    for _ in range(MAX_CHARGE_RETRIES):
        if payments.capture(card_token, amount, reference=ride_id):
            return Charge(ride_id, amount, "charged")
    payments.release(card_token, reference=ride_id)
    return Charge(ride_id, amount, "failed")
