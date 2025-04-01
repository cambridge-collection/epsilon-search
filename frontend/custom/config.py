#!/usr/bin/env python3
import os

# Mandatory variables
DEFAULT_ROWS = int(os.environ.get("DEFAULT_ROWS", 20))

CORE_MAP = {
    # resource name -> solr core name
    "item": "epsilon",
    "page": "site",
}

facet_query = {
    "facet": {
        "f1-document-type": {
            "type": "terms",
            "field": "facet-document-type",
            "limit": 10,
            "sort": {"index": "asc"}
        },
        "f1-author": {
            "type": "terms",
            "field": "facet-author",
            "limit": 5,
            "sort": {"count": "desc"}
        },
        "f1-addressee": {
            "type": "terms",
            "field": "facet-addressee",
            "limit": 5,
            "sort": {"count": "desc"}
        },
        "f1-correspondent": {
            "type": "terms",
            "field": "facet-correspondent",
            "limit": 5,
            "sort": {"count": "desc"}
        },
        "f1-repository": {
            "type": "terms",
            "field": "facet-repository",
            "limit": 5,
            "sort": {"index": "asc"}
        },
        "f1-contributor": {
            "type": "terms",
            "field": "facet-contributor",
            "limit": 99,
            "sort": {"index": "asc"}
        },
        ".env": {
            "type": "terms",
            "field": "facet-transcription-available",
            "limit": 5,
            "sort": {"index": "desc"}
        },
        "f1-cdl-images-linked": {
            "type": "terms",
            "field": "facet-cdl-images-linked",
            "limit": 5,
            "sort": {"index": "desc"}
        },
        "f1-decade": {
            "type": "terms",
            "field": "facet-decade",
            "limit": 100,
            "sort": {"index": "asc"},
            "facet": {
                "f1-decade-year": {
                    "type": "terms",
                    "field": "facet-decade-year",
                    "limit": 20,
                    "sort": {"index": "asc"},
                    "facet": {
                        "f1-decade-year-month": {
                            "type": "terms",
                            "field": "facet-decade-year-month",
                            "limit": 24,
                            "sort": {"index": "asc"},
                            "facet": {
                                "f1-decade-year-month-day": {
                                    "type": "terms",
                                    "field": "facet-decade-year-month-day",
                                    "limit": 62,
                                    "sort": {"index": "asc"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
