#!/usr/bin/env python3
import json
from typing import Optional, Annotated

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from frontend.lib.utils import *

origins = [
    "http://localhost:5173",
    "https://epsilon-staging.cudl-sandbox.net",
    "https://epsilon-staging.darwinproject.link",
    "https://epsilon-staging.epsilon.ac.uk",
    "https://staging.cudl-sandbox.net",
    "https://staging.epsilon.ac.uk",
]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(implementation.router)

@app.get("/items")
async def get_items(
        params: Annotated[implementation.ItemsQueryParams, Query()]
):
    solr_params = params.get_solr_params()
    return await get_request("items", **solr_params)

@app.put("/item")
async def update_item(request: Request):
    data = await request.body()
    json_dict = json.loads(data)
    if json_dict.get("facet-document-type") in ["letter", "bibliography", "people", "repository", "documentation", "site"]:
        logger.info(f"Indexing {json_dict.get('fileID')}")
        status_code = await put_item("item", data, {"f": ["$FQN:/**", "/*"]})
    else:
        logger.error(f"Invalid item JSON for fileID: {json_dict.get('fileID')}")
        status_code = INTERNAL_ERROR_STATUS_CODE
    return status_code

@app.delete("/item/{file_id}")
async def delete_item(file_id: str):
    return await delete_resource("item", file_id)
