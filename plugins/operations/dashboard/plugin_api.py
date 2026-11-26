"""Mount operations routes under the authenticated Desktop workspace scope."""
from pathlib import Path

from fastapi import APIRouter, Depends

from plugins.operations.dashboard import (
    analysis_api,
    asset_api,
    browser_api,
    collection_settings_api,
    content_api,
    designer_api,
    library_api,
    model_budget_api,
    plan_api,
    records_api,
    resume_api,
    review_api,
    source_api,
    token_api,
    topics_api,
    visual_api,
    worker_api,
    workspace_api,
    writing_api,
)

router = APIRouter(dependencies=[Depends(workspace_api.scope_dependency)])

for routes in (
    workspace_api.router,
    library_api.router,
    analysis_api.router,
    source_api.router,
    browser_api.router,
    token_api.router,
    model_budget_api.router,
    topics_api.router,
    content_api.router,
    review_api.router,
    writing_api.router,
    collection_settings_api.router,
    visual_api.router,
    designer_api.router,
    plan_api.router,
    worker_api.router,
    asset_api.router,
    records_api.router,
    resume_api.router,
):
    router.include_router(routes)

# Development tooling is absent from release payloads and wheels.
_source_root = Path(__file__).resolve().parents[3]
if (_source_root / ".git").exists() and (_source_root / "devtools/operations_debug.py").is_file():
    from devtools.operations_debug import router as debug_router
    router.include_router(debug_router)
