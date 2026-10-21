#!/usr/bin/env python3
from typing import Union, List

import httpx
from fastapi import HTTPException

from frontend.defaults import *


def stringify(p: Union[List, any]) -> str:
    if isinstance(p, list):
        return " ".join(map(str, p))
    return str(p)

def listify(p: any) -> List:
    return p if isinstance(p, list) else [p]

# Is the following needed?
# def ensure_urlencoded(var, safe=""):
#     if isinstance(var, str):
#         return urllib.parse.quote(urllib.parse.unquote(var), safe=safe)
#     elif isinstance(var, dict):
#         return {k: ensure_urlencoded(v, safe) for k, v in var.items() if v is not None}
#     elif isinstance(var, list):
#         return [ensure_urlencoded(item, safe) for item in var]
#     return var

def update_solr_response(result: dict, kwargs: dict) -> dict:
    """
    If the keyword 'original_sort' is present in kwargs and the response contains a sort
    parameter in its responseHeader, update that sort value with kwargs["original_sort"].
    """
    if "original_sort" in kwargs and "sort" in result.get("responseHeader", {}).get("params", {}):
        result["responseHeader"]["params"]["sort"] = kwargs["original_sort"]
    return result


def http_exception_from_request_error(e: httpx.HTTPError) -> HTTPException:
    response = getattr(e, "response", None)
    if response is None:
        return HTTPException(status_code=502, detail=str(e).split(":")[-1])
    try:
        results = response.json()
    except ValueError:
        results = {}
    # Solr omits responseHeader entirely while its cores are still loading.
    status_code = results.get("responseHeader", {}).get("status") or response.status_code
    detail = results.get("error", {}).get("msg") or response.reason_phrase or str(e)
    return HTTPException(status_code=status_code, detail=detail)


async def delete_resource(resource_type: str, file_id: str) -> int:
    core = implementation.get_core_name(resource_type)
    if not core:
        raise HTTPException(status_code=INTERNAL_ERROR_STATUS_CODE, detail="Invalid resource type")
    delete_query = f"fileID:{file_id}"
    delete_cmd = {"delete": {"query": delete_query}}
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                f"{SOLR_URL}/solr/{core}/update",
                headers={"Content-Type": "application/json; charset=UTF-8"},
                json=delete_cmd,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise http_exception_from_request_error(e)
    return response.status_code

async def get_request(resource_type: str, **kwargs):
    core = implementation.get_core_name(resource_type)
    if not core:
        raise HTTPException(status_code=INTERNAL_ERROR_STATUS_CODE, detail="Invalid resource type")
    params = kwargs.copy()
    params.pop("original_sort", None)

    url = f"{SOLR_URL}/solr/{core}/spell"
    async with httpx.AsyncClient(timeout=SOLR_SEARCH_TIMEOUT) as client:
        try:
            response = await client.get(
                url,
                params=params,
                headers={"Content-Type": "application/json; charset=UTF-8"},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise http_exception_from_request_error(e)
    result = response.json()
    return update_solr_response(result, kwargs)

async def put_item(resource_type: str, data, params):
    core = implementation.get_core_name(resource_type)
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
            raise http_exception_from_request_error(e)
    return response.status_code
