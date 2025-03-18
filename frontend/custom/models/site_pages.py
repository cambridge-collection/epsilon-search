#!/usr/bin/env python3
from typing import Union, List, Optional, Any, Dict, Annotated
import re
import json
import logging
from fastapi import FastAPI, APIRouter, Request, Query, HTTPException, Request, Depends
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator, ConfigDict
import frontend.models.base_query_params as CoreModel
import frontend.custom.implementation as implementation
import frontend.lib.utils as utils

try:
    from frontend.custom.implementation import DEFAULT_ROWS
    DEFAULT_ROWS = implementation.DEFAULT_ROWS
except ImportError:
    DEFAULT_ROWS = 20

logger = logging.getLogger("gunicorn.error")

router = APIRouter()

class PageQueryParams(CoreModel.CoreQueryParams):
    model_config = ConfigDict(populate_by_name=True)
    s_commentary: Optional[Union[str, List[str]]] = Field(default=None, alias="s-commentary")
    s_key_stage: Optional[Union[str, List[str]]] = Field(default=None, alias="s-key-stage")
    s_ages: Optional[Union[str, List[str]]] = Field(default=None, alias="s-ages")
    s_topics: Optional[Union[str, List[str]]] = Field(default=None, alias="s-topics")
    s_Map_theme: Optional[Union[str, List[str]]] = Field(default=None, alias="s-Map theme")
    facet_searchable: Optional[Union[str, List[str]]] = Field(default=True, alias="facet-searchable")

    @field_validator("facet_searchable", mode="before")
    def validate_facet_searchable(cls, value):
        return "true" if value not in ["true", "false"] else value

    def is_facet(self, key: str, value: Any) -> bool:
        return re.match(r"^(facet|s)-.+?$", key)

    def get_solr_params(self) -> dict:
        query_params2, facet_params2 = self.separate_parameters()
        url_params = {**query_params2, **facet_params2}
        print('URL PARAMS:', url_params)
        solr_params = {}

        # Filter out empty parameters.
        set_params = url_params #{k: v for k, v in url_params.items() if v}
        print('SET:', set_params)
        q = []
        fq = []
        #filters = {}
        #expand_clauses = {}


        for name, value in set_params.items():
            print("Processing ", name, value)
            if value:
                if name in ["keyword", "text"]:
                    q.append(f'({utils.stringify(value)})')
                elif re.match(r"^(facet|s)-.+?$", name):
                    for x in utils.listify(value):
                        x_clean = re.sub(r'^"(.+?)"$', r'\1', x)
                        fq.append(f'{name}:"{x_clean}"')
                    #value_clean = re.sub(r'^"(.+?)"$', r'\1', value)
                    #fq.append(f'{name}:"{value_clean}"')
                elif name == "page":
                    page_val = int(value)
                    solr_params["start"] = (page_val - 1) * DEFAULT_ROWS
                elif name == "sort":
                    sort_val = f"sort-{value}" if value in ["author", "addressee", "correspondent", "date", "name"] else "score"
                    sort_order = "desc" if sort_val == "score" else "asc"
                    solr_params["sort"] = f"{sort_val} {sort_order}"
                elif name != "rows":
                    q.append(f'{name}:({utils.stringify(value)})')

        final_q = " ".join(q)
        if final_q in ["['*']", "['']"]:
            final_q = "*"
        solr_params["q"] = final_q if final_q not in ["['*']", "['']"] else "*"
        solr_params["fq"] = fq
        # Merge filters and expand clauses into our parameters.
        #solr_params = {**solr_params, **filters, **expand_clauses}
        # Remove unwanted keys.
        #for k in solr_delete + solr_fields:
        #    solr_params.pop(k, None)
        print('IN FN ', solr_params)
        return solr_params

@router.get("/pages")
async def get_pages(
        request: Request,
        params: Annotated[PageQueryParams, Query()]
):
    query_params, facet_params = params.separate_parameters()
    print(query_params, facet_params)
    solr_params = params.get_solr_params()
    return await utils.get_request("pages", **solr_params)
    #return await get_request("pages", **query_params, **facet_params)

@router.put("/page")
async def update_page(request: Request):
    data = await request.body()
    json_dict = json.loads(data)
    if json_dict.get("facet-document-type") == "site":
        logger.info(f"Indexing {json_dict.get('fileID')}")
        status_code = await utils.put_item("page", data, {"f": ["$FQN:/**"]})
    else:
        logger.error(f"Invalid site JSON for fileID: {json_dict.get('fileID')}")
        status_code = utils.INTERNAL_ERROR_STATUS_CODE
    return status_code

@router.delete("/page/{file_id}")
async def delete_collection(file_id: str):
    return await utils.delete_resource("page", file_id)
