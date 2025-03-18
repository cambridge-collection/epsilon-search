#!/usr/bin/env python3
from typing import Optional
import re
#from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
#import frontend.models.base_query_params as CoreModel
#from frontend.lib import utils
from fastapi import APIRouter

# Import routers from the models subdirectory
from frontend.custom.models.site_pages import router as pages_router
from frontend.custom.models.items import router as items_router, ItemsQueryParams

router = APIRouter()

# Include the routers from pages and docs.
router.include_router(pages_router)
router.include_router(items_router)

facet_query = {"facet":{"f1-document-type":{"type":"terms","field":"facet-document-type","limit":10,"sort":{"index":"asc"}},"f1-author":{"type":"terms","field":"facet-author","limit":5,"sort":{"count":"desc"}},"f1-addressee":{"type":"terms","field":"facet-addressee","limit":5,"sort":{"count":"desc"}},"f1-correspondent":{"type":"terms","field":"facet-correspondent","limit":5,"sort":{"count":"desc"}},"f1-repository":{"type":"terms","field":"facet-repository","limit":5,"sort":{"index":"asc"}},"f1-volume":{"type":"terms","field":"facet-volume","limit":5,"sort":{"index":"asc"}},"f1-entry-cancelled":{"type":"terms","field":"facet-entry-cancelled","limit":5,"sort":{"index":"desc"}},"f1-document-online":{"type":"terms","field":"facet-document-online","limit":5,"sort":{"index":"desc"}},"f1-letter-published":{"type":"terms","field":"facet-letter-published","limit":5,"sort":{"index":"desc"}},"f1-translation-published":{"type":"terms","field":"facet-translation-published","limit":5,"sort":{"index":"desc"}},"f1-footnotes-published":{"type":"terms","field":"facet-footnotes-published","limit":5,"sort":{"index":"desc"}},"f1-has-tnotes":{"type":"terms","field":"facet-has-tnotes","limit":5,"sort":{"index":"desc"}},"f1-has-cdnotes":{"type":"terms","field":"facet-has-cdnotes","limit":5,"sort":{"index":"desc"}},"f1-has-annotations":{"type":"terms","field":"facet-has-annotations","limit":5,"sort":{"index":"desc"}},"f1-linked-to-cudl-images":{"type":"terms","field":"facet-linked-to-cudl-images","limit":5,"sort":{"index":"desc"}},"f1-darwin-letter":{"type":"terms","field":"facet-darwin-letter","limit":5,"sort":{"index":"desc"}},"f1-year":{"type":"terms","field":"facet-year","limit":100,"sort":{"index":"asc"},"facet":{"f1-year-month":{"type":"terms","field":"facet-year-month","limit":24,"sort":{"index":"asc"},"facet":{"f1-year-month-day":{"type":"terms","field":"facet-year-month-day","limit":62,"sort":{"index":"asc"}}}}}}}}


ITEM_CORE = "dcp"
PAGE_CORE = "site"
CORE_MAP = {
    "item": ITEM_CORE,
    "page": PAGE_CORE,
}

DEFAULT_ROWS=20


def get_core_name(resource_type: str) -> Optional[str]:
    resource = re.sub(r's$', '', resource_type.lower())
    return CORE_MAP.get(resource)


