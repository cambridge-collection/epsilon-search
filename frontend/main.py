#!/usr/bin/env python3
import json
from typing import Union, List, Optional, Annotated, Any, Tuple, Dict
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from frontend.lib.utils import *
#logger = logging.getLogger("gunicorn.error")

origins = [
    "http://localhost:5173",
    "https://darwin-editorial.cudl-sandbox.net",
    "https://darwin-editorial.darwinproject.ac.uk",
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

@app.get("/json/letters")
async def get_letters(
        q: Optional[List[str]] = Query(None),
        fq: Optional[List[str]] = Query(None),
):
    fq = fq or []
    for clause in ["facet-document-type:letter", "facet-entry-cancelled:No", "facet-darwin-letter:Yes"]:
        if clause not in fq:
            fq.append(clause)
    q_final = " AND ".join(q) if q else ""
    params = {
        "q": q_final,
        "fq": fq,
        "sort": "sort-date asc",
        "rows": 99999,
        "fl": "id,path,title,date,displayDate,dateStart,direction,deprecated,sender,recipient,url,summary,search-correspondent-id",
        "hl": "false",
        "facet.field": ["direction", "facet-document-type"],
    }
    result = await get_request("items", **params)
    counts = {"To": 0, "From": 0, "3rdParty": 0, "letter": 0, "people": 0, "bibliography": 0}
    dir_facet = result.get("facet_counts", {}).get("facet_fields", {}).get("direction", [])
    type_facet = result.get("facet_counts", {}).get("facet_fields", {}).get("facet-document-type", [])
    facets = dir_facet + type_facet
    for key, value in zip(facets[::2], facets[1::2]):
        counts[key] = value
    output = {
        "requestURI": "/search?f1-document-type=letter&f2-darwin-letter=Yes&f3-entry-cancelled=No&rmode=json&sort=date",
        "dateTimeFormat": "iso8601",
        "statistics": [
            {
                "letter": [
                    {
                        "count": counts["letter"],
                        "darwinSent": counts["From"],
                        "darwinReceived": counts["To"],
                        "3rdParty": counts["3rdParty"],
                    }
                ]
            },
            {"people": [{"count": counts["people"]}]},
            {"bibliographies": [{"count": counts["bibliography"]}]},
        ],
        "letters": result.get("response", {}).get("docs", []),
    }
    return output

@app.get("/summary")
async def get_summary(
        q: Optional[List[str]] = Query(None),
        fq: Optional[str] = None,
):
    q_final = " AND ".join(q) if q else ""
    params = {"q": q_final, "fq": fq}
    result = await get_request("items", **params)
    if "docs" in result.get("response", {}):
        del result["response"]["docs"]
    return result

@app.put("/item")
async def update_item(request: Request):
    data = await request.body()
    json_dict = json.loads(data)
    if json_dict.get("facet-document-type") in ["letter", "bibliography", "people", "repository", "documentation"]:
        logger.info(f"Indexing {json_dict.get('fileID')}")
        status_code = await put_item("item", data, {"f": ["$FQN:/**", "/*"]})
    else:
        logger.error(f"Invalid item JSON for fileID: {json_dict.get('fileID')}")
        status_code = INTERNAL_ERROR_STATUS_CODE
    return status_code

@app.delete("/item/{file_id}")
async def delete_item(file_id: str):
    return await delete_resource("item", file_id)
