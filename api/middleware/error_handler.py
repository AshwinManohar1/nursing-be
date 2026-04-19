from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import traceback
from api.utils.logger import get_logger

logger = get_logger("error_handler")

def add_exception_handlers(app: FastAPI):
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_details = {
            "message": str(exc),
            "url": str(request.url),
            "method": request.method,
            "stack": traceback.format_exc(),
        }
        logger.error(f"Unhandled error: {error_details}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": str(exc) or "Internal Server Error",
                "data": {},
                "timestamp": "TODO: add datetime.utcnow().isoformat()"
            },
        )

    @app.middleware("http")
    async def not_found_middleware(request: Request, call_next):
        try:
            response = await call_next(request)
            if response.status_code == 404:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "message": f"Route {request.url.path} not found",
                        "data": {},
                        "timestamp": "TODO: add datetime.utcnow().isoformat()"
                    },
                )
            return response
        except Exception as e:
            raise e