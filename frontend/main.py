#!/usr/bin/env python3
import json
import logging
import re
import os
from typing import Union, List, Optional, Annotated, Any, Tuple, Dict
import httpx
from fastapi import FastAPI, Request, Query, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
import frontend.custom.implementation as implementation
import frontend.lib.utils as utils

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

    url = f"{SOLR_URL}/solr/{core}/spell"
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.get(
                url,
                params=params,
                headers={"Content-Type": "application/json; charset=UTF-8"},
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            detail = e.response.text if e.response is not None else str(e)
            raise HTTPException(status_code=502, detail=detail.split(":")[-1])
    result = response.json()
    return implementation.update_solr_response(result, kwargs)

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

DEFAULT_ROWS = 20


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
                    solr_params["start"] = (page_val - 1) * 20
                elif name != "rows" and name != "sort":
                    q.append(f'{name}:({utils.stringify(value)})')

        final_q = " ".join(q)
        if final_q in ["['*']", "['']"]:
            final_q = "*"
        solr_params["q"] = final_q if final_q not in ["['*']", "['']"] else "*"
        solr_params["fq"] = fq

        return solr_params



class PageQueryParams(CoreQueryParams):
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
                    solr_params["start"] = (page_val - 1) * 20
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


@app.get("/pages")
async def get_pages(
        request: Request,
        params: Annotated[PageQueryParams, Query()]
):
    query_params, facet_params = params.separate_parameters()
    print(query_params, facet_params)
    solr_params = params.get_solr_params()
    return await get_request("pages", **solr_params)
    #return await get_request("pages", **query_params, **facet_params)


class ItemsQueryParams(CoreQueryParams):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    expand: Optional[str] = None
    text: Optional[Union[str, List[str]]] = Field(default=None)
    section_type: Optional[str] = Field(default=None, alias="sectionType")
    search_author: Optional[str] = Field(default=None, alias="search-author")
    search_addressee: Optional[str] = Field(default=None, alias="search-addressee")
    search_correspondent: Optional[str] = Field(default=None, alias="search-correspondent")
    search_repository: Optional[str] = Field(default=None, alias="search-repository")
    exclude_cancelled: Optional[str] = Field(default=None, alias="exclude-cancelled")
    exclude_widedate: Optional[str] = Field(default=None, alias="exclude-widedate")
    year: Optional[Union[int, str]] = None
    month: Optional[Union[int, str]] = None
    day: Optional[Union[int, str]] = None
    year_max: Optional[Union[int, str]] = Field(default=None, alias="year-max")
    month_max: Optional[Union[int, str]] = Field(default=None, alias="month-max")
    day_max: Optional[Union[int, str]] = Field(default=None, alias="day-max")
    search_date_type: Optional[str] = Field(default="on", alias="search-date-type")

    # Canonical facets
    f1_document_type: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-document-type")
    f1_author: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-author")
    f1_addressee: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-addressee")
    f1_correspondent: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-correspondent")
    f1_year: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-year")
    f1_repository: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-repository")
    f1_volume: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-volume")
    f1_entry_cancelled: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-entry-cancelled")
    f1_document_online: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-document-online")
    f1_letter_published: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-letter-published")
    f1_translation_published: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-translation-published")
    f1_footnotes_published: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-footnotes-published")
    f1_has_tnotes: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-has-tnotes")
    f1_has_cdnotes: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-has-cdnotes")
    f1_has_annotations: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-has-annotations")
    f1_linked_to_cudl_images: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-linked-to-cudl-images")
    f1_darwin_letter: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-darwin-letter")


    #dynamic_facets: Dict[str, List[str]] = Field(default_factory=dict)

    @model_validator(mode="before")
    def filter_and_extract_dynamic_facets(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        # Pattern matches keys starting with 'f', followed by digits, and then one or more hyphen-separated alphanumeric segments.
        facet_pattern = re.compile(r"^f[0-9]+((-[a-zA-Z0-9]+)+)$")
        defined_fields = set(cls.model_fields.keys())

        for key in list(values.keys()):
            if key not in defined_fields:
                match = facet_pattern.match(key)
                if match:
                    facet_value = values.pop(key)
                    facet_value = facet_value if isinstance(facet_value, list) else [facet_value]
                    new_key = f"f1{match.group(1)}"
                    if new_key in values:
                        existing = values[new_key]
                        if not isinstance(existing, list):
                            existing = [existing]
                        existing.extend(facet_value)
                        values[new_key] = existing
                    else:
                        values[new_key] = facet_value
                else:
                    values.pop(key)
        return values

    @field_validator("rows", mode="after")
    def validate_rows_items(cls, value):
        return 20 if value not in (8, 20) else value

    def is_facet(self, key: str, value: Any) -> bool:
        return re.match(r"^f[0-9]+-.+?$", key) is not None

    def generate_datestring(self, year, month, day):
        if year:
            # Only form a date string if month is provided when day is provided
            if day and not month:
                return None
            parts = [str(x).zfill(2) for x in [year, month, day] if x is not None]
            return "-".join(parts)
        return None

    def get_solr_params(self) -> dict:
        query_params2, facet_params2 = self.separate_parameters()
        url_params = {**query_params2, **facet_params2}

        # Mapping for text translations
        translation_key = {
            "transcribed": "content_textual-content",
            "footnote": "content_footnotes",
            "summary": "content_summary",
        }
        # These fields will be removed later.
        solr_delete = ["text", "keyword", "sectionType", "search-date-type"]
        solr_fields = ["_text_", "content_textual-content", "content_footnotes", "content_summary"]
        remap_fields = [
            "exclude-widedate",
            "exclude-cancelled",
            "search-correspondent",
            "search-addressee",
            "search-author",
            "search-repository",
            "day",
            "month",
            "dateRange",
        ]
        solr_params = {}

        # Filter out empty parameters.
        set_params = url_params #{k: v for k, v in url_params.items() if v}
        print('SET:', set_params)
        q = []
        fq = []
        filters = {}
        expand_clauses = {}

        # Remove exclusionary boolean params that only make sense in the affirmative.
        for p in ["exclude-widedate", "exclude-cancelled"]:
            if set_params.get(p, "").lower() == "no":
                set_params.pop(p, None)

        # Remap text field based on sectionType
        if set_params.get("text") and set_params.get("sectionType") in translation_key:
            key = translation_key[set_params["sectionType"]]
            set_params[key] = set_params.pop("text")
            set_params.pop("sectionType", None)

        # Date processing
        date_min = self.generate_datestring(set_params.get("year"), set_params.get("month"), set_params.get("day"))
        date_max = self.generate_datestring(set_params.get("year-max"), set_params.get("month-max"), set_params.get("day-max"))
        search_date_type = set_params.get("search-date-type")
        if date_min or search_date_type == "between":
            for k in ["year", "month", "day", "year-max", "month-max", "day-max", "search-date-type"]:
                set_params.pop(k, None)
            predicate_type = "Within"
            if date_max or search_date_type == "between":
                date_max_final = date_max if date_max else "2009-02-12"
                date_min_final = date_min if date_min else "1609-02-12"
                predicate_type = "Intersects"
                date_range = f"[{date_min_final} TO {date_max_final}]"
            else:
                if search_date_type == "after":
                    predicate_type = "Intersects"
                    date_range = f"[{date_min} TO 2009-02-12]"
                elif search_date_type == "before":
                    predicate_type = "Intersects"
                    date_range = f"[1609-02-12 TO {date_min}]"
                else:
                    date_range = date_min
            if date_range:
                fq.append(f'{{!field f=dateRange op={predicate_type}}}{date_range}')
        else:
            set_params.pop("search-date-type", None)

        for name, value in set_params.items():
            print("Processing ", name, value)
            if value:
                if name in remap_fields:
                    q.append(f'{name}:({utils.stringify(value)})')
                elif name in ["keyword", "text"]:
                    q.append(f'({utils.stringify(value)})')
                elif re.match(r"^f[0-9]+-date$", name):
                    val_list = utils.listify(value)
                    fields = ["facet-year", "facet-year-month", "facet-year-month-day"]
                    for date in sorted(val_list):
                        date_clean = re.sub(r'^"(.+?)"$', r'\1', date)
                        date_parts = date_clean.split("::")
                        num_parts = len(date_parts)
                        solr_name = fields[min(num_parts - 1, len(fields) - 1)]
                        for index, field in enumerate(fields):
                            if index >= num_parts - 1:
                                filters[f"f.{field}.facet.contains"] = date_clean
                            else:
                                filters[f"f.{field}.facet.contains"] = "::".join(date_parts[: index + 1])
                        fq.append(f'{solr_name}:"{date_clean}"')
                elif re.match(r"^f[0-9]+-.+?$", name):
                    solr_name = re.sub(r"^f[0-9]+-(.+?)$", r"facet-\1", name)
                    for x in utils.listify(value):
                        x_clean = re.sub(r'^"(.+?)"$', r'\1', x)
                        fq.append(f'{solr_name}:"{x_clean}"')
                elif re.match(r"^(facet|s)-.+?$", name):
                    value_clean = re.sub(r'^"(.+?)"$', r'\1', value)
                    fq.append(f'{name}:"{value_clean}"')
                elif name == "page":
                    page_val = int(value)
                    solr_params["start"] = (page_val - 1) * 20
                elif name == "sort":
                    sort_val = f"sort-{value}" if value in ["author", "addressee", "correspondent", "date", "name"] else "score"
                    sort_order = "desc" if sort_val == "score" else "asc"
                    solr_params["sort"] = f"{sort_val} {sort_order}"
                elif name == "expand":
                    if value in ["author", "addressee", "correspondent", "repository", "volume"]:
                        expand_clauses[f"f.facet-{value}.facet.limit"] = "-1"
                        expand_clauses[f"f.facet-{value}.facet.sort"] = "-1"
                elif name != "rows":
                    q.append(f'{name}:({utils.stringify(value)})')

        final_q = " ".join(q)
        if final_q in ["['*']", "['']"]:
            final_q = "*"
        solr_params["q"] = final_q if final_q not in ["['*']", "['']"] else "*"
        solr_params["fq"] = fq
        # Merge filters and expand clauses into our parameters.
        solr_params = {**solr_params, **filters, **expand_clauses}
        # Remove unwanted keys.
        for k in solr_delete + solr_fields:
            solr_params.pop(k, None)
        return solr_params



@app.get("/items")
async def get_items(
        params: Annotated[ItemsQueryParams, Query()]
):
    query_params, facet_params = params.separate_parameters()
    print('PARAMS:', query_params, facet_params)
    solr = params.get_solr_params()
    print('SOLR:', solr)
    solr_params = params.get_solr_params()
    return await get_request("items", **solr_params)
    #return await get_request("items", **query_params, **facet_params)

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
