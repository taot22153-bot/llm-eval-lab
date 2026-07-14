from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm_eval_lab.application_versions import router as application_versions_router
from llm_eval_lab.config import get_settings

app = FastAPI(title="LLM Eval Lab", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(application_versions_router)
