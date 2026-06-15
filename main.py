from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse

from app.database import engine, Base
from app.routers import (
    medicines_router,
    baby_router,
    records_router,
    restock_router,
    risk_router,
    statistics_router
)
from app.utils import success_response, error_response

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="家庭宝宝常备药有效期监控与用药风险提醒 API",
    description="提供药品档案管理、有效期监控、月龄适配校验、风险提醒、补货建议和用药记录等功能",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(medicines_router)
app.include_router(baby_router)
app.include_router(records_router)
app.include_router(restock_router)
app.include_router(risk_router)
app.include_router(statistics_router)


@app.get("/", tags=["根路径"])
def root():
    return success_response(
        data={
            "app_name": "家庭宝宝常备药有效期监控与用药风险提醒服务",
            "version": "1.0.0",
            "docs": "/docs",
            "redoc": "/redoc"
        },
        message="服务运行正常"
    )


@app.get("/health", tags=["健康检查"])
def health_check():
    return success_response(data={"status": "healthy"}, message="服务健康")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    error_messages = []
    for err in errors:
        loc = " -> ".join([str(x) for x in err.get("loc", [])])
        msg = err.get("msg", "")
        error_messages.append(f"[{loc}]: {msg}")

    message = "参数校验失败: " + "; ".join(error_messages) if error_messages else "参数校验失败"
    return JSONResponse(
        status_code=200,
        content=error_response(code=422, message=message, data={"detail": errors})
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=200,
        content=error_response(code=exc.status_code, message=exc.detail)
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content=error_response(code=500, message=f"服务器内部错误: {str(exc)}")
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
