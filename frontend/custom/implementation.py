#!/usr/bin/env python3
import re
from typing import Optional

from fastapi import APIRouter

from frontend.custom.config import CORE_MAP
from frontend.custom.models.items import router as items_router, ItemsQueryParams # ItemsQueryParams is used by main
# Import routers from the models subdirectory
from frontend.custom.models.site_pages import router as pages_router

router = APIRouter()

router.include_router(pages_router)
router.include_router(items_router)


def get_core_name(resource_type: str) -> Optional[str]:
    resource = re.sub(r's$', '', resource_type.lower())
    return CORE_MAP.get(resource)


