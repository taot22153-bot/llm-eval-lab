from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm_eval_lab.application_versions import router as application_versions_router
from llm_eval_lab.config import get_settings
from llm_eval_lab.evaluation_runs import reconcile_interrupted_evaluation_runs
from llm_eval_lab.evaluation_runs import router as evaluation_runs_router
from llm_eval_lab.evaluation_suites import router as evaluation_suites_router
from llm_eval_lab.human_review import router as human_review_router
from llm_eval_lab.test_case_executions import reconcile_interrupted_test_case_executions
from llm_eval_lab.test_case_executions import router as test_case_executions_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    reconcile_interrupted_test_case_executions()
    reconcile_interrupted_evaluation_runs()
    yield


app = FastAPI(title="LLM Eval Lab", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)
app.include_router(application_versions_router)
app.include_router(evaluation_suites_router)
app.include_router(evaluation_runs_router)
app.include_router(test_case_executions_router)
app.include_router(human_review_router)
