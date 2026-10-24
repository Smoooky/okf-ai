"""Wheelo rides API: POST /rides starts a ride on a scooter."""

import uuid

import billing
from auth import refresh  # noqa: F401  (token checks live in the auth middleware)

MIN_BATTERY_PERCENT = 15


def start_ride(db, payments, user, scooter_id: str) -> dict:
    """POST /rides  body: {"scooter_id": "..."}  ->  201 {"ride_id": "...", "status": "active"}"""
    scooter = db.scooters.get(scooter_id)
    if scooter is None:
        return {"status": 404, "error": "scooter_not_found"}
    if scooter.status != "available":
        return {"status": 409, "error": "scooter_busy"}
    if scooter.battery_percent < MIN_BATTERY_PERCENT:
        return {"status": 409, "error": "low_battery"}
    if user.card_token is None:
        return {"status": 402, "error": "no_payment_method"}

    ride_id = str(uuid.uuid4())
    billing.hold(payments, user.card_token, ride_id)
    db.rides.insert(id=ride_id, user_id=user.id, scooter_id=scooter_id, status="active")
    db.scooters.update(scooter_id, status="in_ride")
    return {"status": 201, "ride_id": ride_id, "ride_status": "active"}
