#!/usr/bin/env python3
import json
import logging
import re
import os
from typing import Union, List, Optional
import httpx
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import frontend.custom.implementation as implementation

logger = logging.getLogger("gunicorn.error")

origins = [
    "http://localhost:5173",
    "https://darwin-editorial.cudl-sandbox.net",
    "https://darwin-editorial.darwinproject.ac.uk",
]

# Get environment variables and ensure required ones are set.
SOLR_HOST = os.getenv("SOLR_HOST")
if not SOLR_HOST:
    raise EnvironmentError("ERROR: SOLR_HOST environment variable not set")
SOLR_PORT = os.getenv("SOLR_PORT")
if not SOLR_PORT:
    raise EnvironmentError("ERROR: SOLR_PORT environment variable not set")

SOLR_URL = f"http://{SOLR_HOST}:{SOLR_PORT}"

INTERNAL_ERROR_STATUS_CODE = 500


def get_core_name(resource_type: str) -> Optional[str]:
    resource = re.sub(r's$', '', resource_type.lower())
    return implementation.CORE_MAP.get(resource)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def delete_resource(resource_type: str, file_id: str) -> int:
    core = get_core_name(resource_type)
    if not core:
        return INTERNAL_ERROR_STATUS_CODE
    delete_query = f"fileID:{file_id}"
    delete_cmd = {"delete": {"query": delete_query}}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{SOLR_URL}/solr/{core}/update",
            headers={"Content-Type": "application/json; charset=UTF-8"},
            json=delete_cmd,
        )
    return response.status_code

async def get_request(resource_type: str, **kwargs):
    core = get_core_name(resource_type)
    if not core:
        raise HTTPException(status_code=INTERNAL_ERROR_STATUS_CODE, detail="Invalid resource type")
    params = kwargs.copy()
    params.pop("original_sort", None)
    solr_params = implementation.translate_params(core, **params)
    url = f"{SOLR_URL}/solr/{core}/spell"
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.get(
                url,
                params=solr_params,
                headers={"Content-Type": "application/json; charset=UTF-8"},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            detail = e.response.text if e.response is not None else str(e)
            raise HTTPException(status_code=502, detail=detail.split(":")[-1])
    result = response.json()
    return implementation._update_solr_response(result, kwargs)

async def put_item(resource_type: str, data, params):
    core = get_core_name(resource_type)
    if not core:
        raise HTTPException(status_code=INTERNAL_ERROR_STATUS_CODE, detail="Invalid resource type")
    path = "update/json/docs"
    url = f"{SOLR_URL}/solr/{core}/{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                url,
                params=params,
                headers={"Content-Type": "application/json; charset=UTF-8"},
                data=data,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise e
    return response.status_code

@app.get("/pages")
async def get_pages(
        request: Request,
        keyword: Optional[List[str]] = Query(None),
        s_commentary: Optional[str] = Query(None, alias="s-commentary"),
        s_key_stage: Optional[str] = Query(None, alias="s-key-stage"),
        s_ages: Optional[str] = Query(None, alias="s-ages"),
        s_topics: Optional[str] = Query(None, alias="s-topics"),
        s_Map_theme: Optional[str] = Query(None, alias="s-Map theme"),
        facet_searchable: Optional[str] = Query(None, alias="facet-searchable"),
        sort: Optional[str] = None,
        rows: Optional[int] = None,
        page: Optional[int] = 1,
):
    q_final = " ".join(keyword) if keyword else ""
    rows_final = rows if rows in [10, 20] else 20
    facets = {k: v for k, v in request.query_params.items() if re.match(r"^(facet|s)-.+?$", k)}
    if facet_searchable not in ["true", "false"]:
        facets["facet-searchable"] = "true"
    params = {"keyword": q_final, "sort": sort, "page": page, "rows": rows_final}
    result = await get_request("pages", **params, **facets)
    return result

@app.get("/items")
async def get_items(
        request: Request,
        sort: Optional[str] = None,
        page: Optional[int] = 1,
        rows: Optional[int] = None,
        expand: Optional[str] = None,
        keyword: Optional[List[str]] = Query(None),
        text: Optional[List[str]] = Query(None),
        section_type: Optional[str] = Query(None, alias="sectionType"),
        search_author: Optional[str] = Query(None, alias="search-author"),
        search_addressee: Optional[str] = Query(None, alias="search-addressee"),
        search_correspondent: Optional[str] = Query(None, alias="search-correspondent"),
        search_repository: Optional[str] = Query(None, alias="search-repository"),
        exclude_cancelled: Optional[str] = Query(None, alias="exclude-cancelled"),
        exclude_widedate: Optional[str] = Query(None, alias="exclude-widedate"),
        year: Optional[Union[int, str]] = None,
        month: Optional[Union[int, str]] = None,
        day: Optional[Union[int, str]] = None,
        year_max: Optional[Union[int, str]] = Query(None, alias="year-max"),
        month_max: Optional[Union[int, str]] = Query(None, alias="month-max"),
        day_max: Optional[Union[int, str]] = Query(None, alias="day-max"),
        search_date_type: Optional[str] = Query("on", alias="search-date-type"),
):
    facets = {
        k: request.query_params.getlist(k)
        for k in request.query_params
        if re.match(r"^f[0-9]+-.+?$", k)
    }
    rows_final = rows if rows in [8, 20] else 20
    params = {
        "sort": sort,
        "page": page,
        "expand": expand,
        "rows": rows_final,
        "text": text,
        "sectionType": section_type,
        "keyword": keyword,
        "search-addressee": search_addressee,
        "search-author": search_author,
        "search-correspondent": search_correspondent,
        "search-repository": search_repository,
        "exclude-cancelled": exclude_cancelled,
        "exclude-widedate": exclude_widedate,
        "year": year,
        "month": month,
        "day": day,
        "year-max": year_max,
        "month-max": month_max,
        "day-max": day_max,
        "search-date-type": search_date_type,
    }
    result = await get_request("items", **params, **facets)
    return result

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

@app.put("/page")
async def update_page(request: Request):
    data = await request.body()
    json_dict = json.loads(data)
    if json_dict.get("facet-document-type") == "site":
        logger.info(f"Indexing {json_dict.get('fileID')}")
        status_code = await put_item("page", data, {"f": ["$FQN:/**"]})
    else:
        logger.error(f"Invalid site JSON for fileID: {json_dict.get('fileID')}")
        status_code = INTERNAL_ERROR_STATUS_CODE
    return status_code

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

@app.delete("/page/{file_id}")
async def delete_collection(file_id: str):
    return await delete_resource("page", file_id)
