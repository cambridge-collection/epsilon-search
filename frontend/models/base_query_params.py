#!/usr/bin/env python3
from sys import implementation
from typing import List, Optional, Union, Dict, Any, Tuple
import re
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from frontend.lib import utils

#try:
#    from frontend.custom.implementation import DEFAULT_ROWS
#except ImportError:
DEFAULT_ROWS = 20

print(DEFAULT_ROWS)

class CoreQueryParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    keyword: Optional[Union[str, List[str]]] = Field(default=None)
    sort: Optional[Union[str, List[str]]] = None
    rows: Optional[Union[int, List[int]]] = Field(default=DEFAULT_ROWS)
    page: Optional[Union[int, List[int]]] = 1

    @field_validator("keyword", mode="before")
    def join_keywords(cls, value):
        return " ".join(value) if isinstance(value, list) else value

    @field_validator("sort", mode="before")
    def take_first_sort(cls, value):
        return value[0] if isinstance(value, list) and value else value

    @field_validator("rows", mode="before")
    def take_first_rows(cls, value):
        return value[0] if isinstance(value, list) and value else value

    @field_validator("rows")
    def validate_rows(cls, value):
        return DEFAULT_ROWS if value not in (10, 20) else value

    @field_validator("page", mode="before")
    def take_first_page(cls, value):
        return value[0] if isinstance(value, list) and value else value

    def is_facet(self, key: str, value: Any) -> bool:
        return key.startswith("facet-")

    def separate_parameters(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # Dump the model data with aliases, excluding None values.
        data = self.model_dump(by_alias=True, exclude_none=True)

        params: Dict[str, Any] = {}
        facets: Dict[str, Any] = {}

        def is_empty(val: Any) -> bool:
            if isinstance(val, str):
                return val.strip() == ""
            if isinstance(val, list):
                if not val:
                    return True
                return all(isinstance(item, str) and item.strip() == "" for item in val)
            return False

        for key, value in data.items():
            if is_empty(value):
                continue
            if self.is_facet(key, value):
                facets[key] = value
            else:
                params[key] = value

        return params, facets

    def get_solr_params(self) -> dict:
        query_params2, facet_params2 = self.separate_parameters()
        url_params = {**query_params2, **facet_params2}

        solr_params = {}

        # Filter out empty parameters.
        #set_params = {k: v for k, v in url_params.items() if v}
        #print('SET:', set_params)
        q = []
        fq = []

        for name, value in url_params.items():
            print('HI:', name, value)
            if value:
                if re.match(r"^facet-.+?$", name):
                    solr_name = re.sub(r"^f[0-9]+-(.+?)$", r"facet-\1", name)
                    for x in utils.listify(value):
                        x_clean = re.sub(r'^"(.+?)"$', r'\1', x)
                        fq.append(f'{solr_name}:"{x_clean}"')
                elif name == "page":
                    page_val = int(value)
                    solr_params["start"] = (page_val - 1) * DEFAULT_ROWS
                elif name != "rows" and name != "sort":
                    q.append(f'{name}:({utils.stringify(value)})')

        final_q = " ".join(q)
        if final_q in ["['*']", "['']"]:
            final_q = "*"
        solr_params["q"] = final_q if final_q not in ["['*']", "['']"] else "*"
        solr_params["fq"] = fq

        return solr_params
