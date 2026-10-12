from fastapi import APIRouter

from app.api.v1 import (
    auth,
    availability,
    channel_connections,
    folios,
    gst,
    guests,
    hotel,
    night_audit,
    onboarding,
    reports,
    reservations,
    room_types,
    rooms,
    tape_chart,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(onboarding.router)
api_router.include_router(hotel.router)
api_router.include_router(room_types.router)
api_router.include_router(rooms.router)
api_router.include_router(guests.router)
api_router.include_router(availability.router)
api_router.include_router(reservations.router)
api_router.include_router(tape_chart.router)
api_router.include_router(folios.router)
api_router.include_router(gst.router)
api_router.include_router(night_audit.router)
api_router.include_router(reports.router)
api_router.include_router(channel_connections.router)
api_router.include_router(webhooks.router)
