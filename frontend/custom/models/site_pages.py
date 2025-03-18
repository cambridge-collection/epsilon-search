#!/usr/bin/env python3
import json
import logging
import re
from typing import Union, List, Optional, Any, Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field, field_validator, ConfigDict

# import frontend.custom.implementation as implementation
import frontend.lib.utils as utils
import frontend.models.base_query_params as CoreModel
from frontend.custom.config import DEFAULT_ROWS

logger = logging.getLogger("gunicorn.error")

router = APIRouter()

class PagesQueryParams(CoreModel.CoreQueryParams):
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
        return re.match(r"^(facet|s)-.+?$", key) is not None

    def get_solr_params(self) -> dict:
        query_params2, facet_params2 = self.separate_parameters()
        url_params = {**query_params2, **facet_params2}
        solr_params = {}

        set_params = url_params
        q = []
        fq = []

        for name, value in set_params.items():
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

        return solr_params

@router.get("/pages")
async def get_pages(params: Annotated[PagesQueryParams, Query()]):
    solr_params = params.get_solr_params()
    return await utils.get_request("pages", **solr_params)

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
