#!/usr/bin/env python3
import re
from typing import Union, List, Optional, Any, Dict

from fastapi import APIRouter
from pydantic import Field, field_validator, model_validator, ConfigDict

import frontend.lib.utils as utils
import frontend.models.base_query_params as CoreModel
from frontend.custom.config import DEFAULT_ROWS

router = APIRouter()

class ItemsQueryParams(CoreModel.CoreQueryParams):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    expand: Optional[str] = None
    text: Optional[Union[str, List[str]]] = Field(default=None)
    section_type: Optional[str] = Field(default=None, alias="sectionType")
    search_author: Optional[str] = Field(default=None, alias="search-author")
    search_addressee: Optional[str] = Field(default=None, alias="search-addressee")
    search_correspondent: Optional[str] = Field(default=None, alias="search-correspondent")
    search_repository: Optional[str] = Field(default=None, alias="search-repository")
    collection: Optional[str] = None
    collection_join: Optional[str] = Field(default=None, alias="collection-join")
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
    f1_decade: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-decade")
    f1_repository: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-repository")
    f1_contributor: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-contributor")
    f1_transcription_available: Optional[Union[str, List[str]]] = Field(default=None, alias="f1_transcription_available")
    f1_cdl_images_linked: Optional[Union[str, List[str]]] = Field(default=None, alias="f1-cdl-images-linked")

    @model_validator(mode="before")
    def filter_and_extract_dynamic_facets(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        # Pattern matches keys starting with 'f', followed by digits, and then one or more hyphen-separated alphanumeric segments.
        facet_pattern = re.compile(r"^f[0-9]+((-[a-zA-Z0-9]+)+)$")
        defined_fields = set(cls.model_fields.keys())
        #print(f"DUMP {values}")
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
        return DEFAULT_ROWS if value not in (10, 20) else value

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
        solr_delete = ["text", "keyword", "sectionType", "search-date-type", "collection-join", "rows"]
        solr_fields = ["_text_", "content_textual-content", "content_footnotes", "content_summary"]
        remap_fields = [
            "exclude-widedate",
            "search-correspondent",
            "search-addressee",
            "search-author",
            "search-repository",
            "day",
            "month",
            "dateRange",
        ]
        solr_params = {}

        set_params = url_params
        q = []
        fq = []
        filters = {}
        expand_clauses = {}

        # Remove exclusionary boolean params that only make sense in the affirmative.
        for p in ["exclude-widedate"]:
            if set_params.get(p, "").lower() == "no":
                set_params.pop(p, None)

        # Remap text field based on sectionType
        if set_params.get("text") and set_params.get("sectionType") in translation_key:
            key = translation_key[set_params["sectionType"]]
            set_params[key] = set_params.pop("text")
            set_params.pop("sectionType", None)
        if set_params.get("sectionType") and not set_params.get("text"):
            set_params.pop("sectionType", None)

        if set_params.get('collection'):
            collections = re.findall(r'("[^"]+")', set_params["collection"])
            collection_join = set_params.get('collection-join','AND')
            joiner = ' ' + collection_join.upper() + ' '
            set_params['collection'] = joiner.join(collections)
        else:
            set_params.pop("collection-join", None)


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
            print('Checking %s' % name)
            if value:
                if name in remap_fields:
                    q.append(f'{name}:({utils.stringify(value)})')
                elif name in ["keyword", "text"]:
                    q.append(f'({utils.stringify(value)})')
                elif re.match(r"^f[0-9]+-date$", name):
                    val_list = utils.listify(value)
                    fields = ["facet-decade", "facet-decade-year", "facet-decade-year-month", "facet-decade-year-month-day"]
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
                elif re.match(r"^facet-.+?$", name):
                    value_clean = re.sub(r'^"(.+?)"$', r'\1', value)
                    fq.append(f'{name}:"{value_clean}"')
                elif name == "page":
                    page_val = int(value)
                    solr_params["start"] = (page_val - 1) * DEFAULT_ROWS
                elif name == "sort":
                    sort_val = f"sort-{value}" if value in ["author", "addressee", "correspondent", "date", "name"] else "score"
                    sort_order = "desc" if sort_val == "score" else "asc"
                    solr_params["sort"] = f"{sort_val} {sort_order}"
                elif name == "expand":
                    if value in ["author", "addressee", "correspondent", "repository", "volume"]:
                        expand_clauses[f"f.facet-{value}.facet.limit"] = "-1"
                        expand_clauses[f"f.facet-{value}.facet.sort"] = "-1"
                elif not name in solr_delete + solr_fields:
                    q.append(f'{name}:({utils.stringify(value)})')

        final_q = " ".join(q)
        if final_q in ["['*']", "['']"]:
            final_q = "*"
        solr_params["q"] = final_q if final_q not in ["['*']", "['']"] else "*"
        solr_params["fq"] = fq
        solr_params = {**solr_params, **filters, **expand_clauses}
        #print(solr_params)
        return solr_params
