from contextlib import asynccontextmanager
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.config import PORT
from api.db import db_manager
from api.middleware.error_handler import add_exception_handlers
from api.utils.rate_limit import limiter
from api.router import chat_router, hospital_router, roster_router, shift_router, staff_router, ward_router, ward_occupancy_router, dashboard_router, login_router, user_router, ward_transfer_router
from api.utils.logger import get_logger
from api.utils.cors import setup_cors


logger = get_logger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Shiftwise service...")
    await db_manager.connect()
    yield
    logger.info("Shutting down Shiftwise service...")
    await db_manager.disconnect()

app = FastAPI(
    title="Shiftwise API",
    version="1.0.0",
    description="Shift Roster Management powered by FastAPI",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

setup_cors(app)
add_exception_handlers(app)

app.include_router(login_router.router)
app.include_router(user_router.router)
app.include_router(staff_router.router, prefix="/api/v1", tags=["Staff"])
app.include_router(shift_router.router, prefix="/api/v1", tags=["Shift"])
app.include_router(roster_router.router, prefix="/api/v1", tags=["Roster"])
app.include_router(chat_router.router, prefix="/api/v1", tags=["AI Chat"])
app.include_router(ward_router.router, prefix="/api/v1", tags=["Ward"])
app.include_router(hospital_router.router, prefix="/api/v1", tags=["Hospital"])
app.include_router(ward_occupancy_router.router, prefix="/api/v1", tags=["Ward Occupancy"])
app.include_router(ward_transfer_router.router, prefix="/api/v1", tags=["Ward Transfer"])
app.include_router(dashboard_router.router, prefix="/api/v1/dashboard", tags=["Dashboard"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
