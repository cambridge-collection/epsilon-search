#!/usr/bin/env python3
from typing import Union, List
import re
import frontend.lib.utils as utils

facet_query = {"facet":{"f1-document-type":{"type":"terms","field":"facet-document-type","limit":10,"sort":{"index":"asc"}},"f1-author":{"type":"terms","field":"facet-author","limit":5,"sort":{"count":"desc"}},"f1-addressee":{"type":"terms","field":"facet-addressee","limit":5,"sort":{"count":"desc"}},"f1-correspondent":{"type":"terms","field":"facet-correspondent","limit":5,"sort":{"count":"desc"}},"f1-repository":{"type":"terms","field":"facet-repository","limit":5,"sort":{"index":"asc"}},"f1-volume":{"type":"terms","field":"facet-volume","limit":5,"sort":{"index":"asc"}},"f1-entry-cancelled":{"type":"terms","field":"facet-entry-cancelled","limit":5,"sort":{"index":"desc"}},"f1-document-online":{"type":"terms","field":"facet-document-online","limit":5,"sort":{"index":"desc"}},"f1-letter-published":{"type":"terms","field":"facet-letter-published","limit":5,"sort":{"index":"desc"}},"f1-translation-published":{"type":"terms","field":"facet-translation-published","limit":5,"sort":{"index":"desc"}},"f1-footnotes-published":{"type":"terms","field":"facet-footnotes-published","limit":5,"sort":{"index":"desc"}},"f1-has-tnotes":{"type":"terms","field":"facet-has-tnotes","limit":5,"sort":{"index":"desc"}},"f1-has-cdnotes":{"type":"terms","field":"facet-has-cdnotes","limit":5,"sort":{"index":"desc"}},"f1-has-annotations":{"type":"terms","field":"facet-has-annotations","limit":5,"sort":{"index":"desc"}},"f1-linked-to-cudl-images":{"type":"terms","field":"facet-linked-to-cudl-images","limit":5,"sort":{"index":"desc"}},"f1-darwin-letter":{"type":"terms","field":"facet-darwin-letter","limit":5,"sort":{"index":"desc"}},"f1-year":{"type":"terms","field":"facet-year","limit":100,"sort":{"index":"asc"},"facet":{"f1-year-month":{"type":"terms","field":"facet-year-month","limit":24,"sort":{"index":"asc"},"facet":{"f1-year-month-day":{"type":"terms","field":"facet-year-month-day","limit":62,"sort":{"index":"asc"}}}}}}}}


ITEM_CORE = "dcp"
PAGE_CORE = "site"
CORE_MAP = {
    "item": ITEM_CORE,
    "page": PAGE_CORE,
}


def generate_datestring(year, month, day):
    if year:
        # Only form a date string if month is provided when day is provided
        if day and not month:
            return None
        parts = [str(x).zfill(2) for x in [year, month, day] if x is not None]
        return "-".join(parts)
    return None

def translate_params(resource_type: str, **url_params) -> dict:
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
    set_params = {k: v for k, v in url_params.items() if v}

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
    date_min = generate_datestring(set_params.get("year"), set_params.get("month"), set_params.get("day"))
    date_max = generate_datestring(set_params.get("year-max"), set_params.get("month-max"), set_params.get("day-max"))
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

def _update_solr_response(result: dict, kwargs: dict) -> dict:
    """
    If the keyword 'original_sort' is present in kwargs and the response contains a sort
    parameter in its responseHeader, update that sort value with kwargs["original_sort"].
    """
    if "original_sort" in kwargs and "sort" in result.get("responseHeader", {}).get("params", {}):
        result["responseHeader"]["params"]["sort"] = kwargs["original_sort"]
    return result
