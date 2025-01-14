#!/usr/bin/env python3

import json
import logging
import re
import os
import requests
import urllib.parse
from typing import Union, List, Literal
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger('gunicorn.error')

origins = [
    "http://localhost:5173",
    "https://darwin-editorial.cudl-sandbox.net",
    "https://darwin-editorial.darwinproject.ac.uk"
]

facet_query = {"facet":{"f1-document-type":{"type":"terms","field":"facet-document-type","limit":10,"sort":{"index":"asc"}},"f1-author":{"type":"terms","field":"facet-author","limit":5,"sort":{"count":"desc"}},"f1-addressee":{"type":"terms","field":"facet-addressee","limit":5,"sort":{"count":"desc"}},"f1-correspondent":{"type":"terms","field":"facet-correspondent","limit":5,"sort":{"count":"desc"}},"f1-repository":{"type":"terms","field":"facet-repository","limit":5,"sort":{"index":"asc"}},"f1-volume":{"type":"terms","field":"facet-volume","limit":5,"sort":{"index":"asc"}},"f1-entry-cancelled":{"type":"terms","field":"facet-entry-cancelled","limit":5,"sort":{"index":"desc"}},"f1-document-online":{"type":"terms","field":"facet-document-online","limit":5,"sort":{"index":"desc"}},"f1-letter-published":{"type":"terms","field":"facet-letter-published","limit":5,"sort":{"index":"desc"}},"f1-translation-published":{"type":"terms","field":"facet-translation-published","limit":5,"sort":{"index":"desc"}},"f1-footnotes-published":{"type":"terms","field":"facet-footnotes-published","limit":5,"sort":{"index":"desc"}},"f1-has-tnotes":{"type":"terms","field":"facet-has-tnotes","limit":5,"sort":{"index":"desc"}},"f1-has-cdnotes":{"type":"terms","field":"facet-has-cdnotes","limit":5,"sort":{"index":"desc"}},"f1-has-annotations":{"type":"terms","field":"facet-has-annotations","limit":5,"sort":{"index":"desc"}},"f1-linked-to-cudl-images":{"type":"terms","field":"facet-linked-to-cudl-images","limit":5,"sort":{"index":"desc"}},"f1-darwin-letter":{"type":"terms","field":"facet-darwin-letter","limit":5,"sort":{"index":"desc"}},"f1-year":{"type":"terms","field":"facet-year","limit":100,"sort":{"index":"asc"},"facet":{"f1-year-month":{"type":"terms","field":"facet-year-month","limit":24,"sort":{"index":"asc"},"facet":{"f1-year-month-day":{"type":"terms","field":"facet-year-month-day","limit":62,"sort":{"index":"asc"}}}}}}}}

if 'SOLR_HOST' in os.environ:
    SOLR_HOST = os.environ['SOLR_HOST']
else:
    print('ERROR: SOLR_HOST environment variable not set')

if 'SOLR_PORT' in os.environ:
    SOLR_PORT = os.environ['SOLR_PORT']
else:
    print('WARN: SOLR_PORT environment variable not set')

SOLR_URL = 'http://%s:%s' % (SOLR_HOST, SOLR_PORT)

INTERNAL_ERROR_STATUS_CODE = 500

# Core names
ITEM_CORE = 'dcp'
PAGE_CORE = 'site'

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_core_name(resource_type: str):
    core = ''

    resource_type_trimmed = re.sub(r's$', '', resource_type)
    if resource_type_trimmed == 'item':
        core = ITEM_CORE
    elif resource_type_trimmed == 'page':
        core = PAGE_CORE

    return core


def get_fieldprefix(val):
    result: str = '_text_'
    if val == 'text':
        result = 'content.html'
    return result

def get_obj_property(key, param):
    result = None
    if key in param:
        result = param[key]
    return result


def stringify(p):
    result = None
    if type(p) == list:
        result = " ".join(p)
    elif not type(p) in [dict, tuple]:
        result = str(p)
    return result

def listify(p):
    result = []
    if type(p) is str:
        result.append(p)
    elif type(p) is list:
        result = p
    else:
        result.append(p)
    return result


def translate_params(resource_type: str, **url_params):
    translation_key = {
        'transcribed': 'content_textual-content',
        'footnote': 'content_footnotes',
        'summary': 'content_summary',
    }
    solr_delete = ['text','keyword', 'sectionType', 'search-date-type']
    solr_fields = ['_text_', 'content_textual-content', 'content_footnotes', 'content_summary']

    # day and month are removed from the set_params array during date processing -- unless they are absolutely
    # necessary for weird impartial searches -- like searching for every letter written in a november.
    # This sort or search doesn't even work on the current site.
    remap_fields = ['exclude-widedate','exclude-cancelled','search-correspondent','search-addressee','search-author','search-repository', 'day', 'month', 'dateRange']
    solr_params = { }
    q = []
    fq = []
    filter={}
    expand_clauses={}
    solr_name = ''

    set_params = {k: v for k, v in url_params.items() if v}
    #print('Set SOLR Params')
    #print(set_params)
    # text field - with sectionType
    # [All] sectionType= -> content.textual_content
    # [Transcriptions only] sectionType=transcribed -> content.transcription
    # [Footnotes] sectionType=footnote -> content.footnotes
    # [Summary] sectionType=summary -> content.summary
    #
    # Date searches
    # year, month, day and year-max, month-max, day-max [max only appears for ranges]
    # Mode of date search
    # search-date-type=on,before,after,between
    #
    # exclude-widedate = Yes/No [Yes by default] --> need to be switched to true/false
    # exclude-cancelled = Yes/No [Yes by default] --> true/false

    # No changes needed for these fields
    # Correspondent search via single text field and radio button - button changes param name in field
    # search-correspondent -> search-correspondent
    # search-addressee -> search-addressee
    # search-author -> search-author
    # search-repository -> search-repository

    # Remove exclusionary boolean params. They only make sense in the affirmative.
    for p in ['exclude-widedate', 'exclude-cancelled']:
        field = get_obj_property(p, set_params)
        if field and field.lower() == 'no':
            set_params.pop(p, None)

    # Tidy compound variable searches
    if get_obj_property('text', set_params) and get_obj_property('sectionType', set_params) in ['transcribed', 'footnote','summary']:
        field_prefix = translation_key[set_params['sectionType']]
        set_params[field_prefix] = set_params['text']
        set_params.pop('text', None)
        set_params.pop('sectionType', None)

    date_min=generate_datestring(get_obj_property('year', set_params),
                        get_obj_property('month', set_params),
                        get_obj_property('day', set_params))
    date_max=generate_datestring(get_obj_property('year-max', set_params),
                                 get_obj_property('month-max', set_params),
                                 get_obj_property('day-max', set_params))

    search_date_type = get_obj_property('search-date-type', set_params)

    #print('%s - %s ' % (date_min, date_max))
    if date_min or search_date_type == 'between':
        for x in ['year', 'month', 'day', 'year-max', 'month-max', 'day-max', 'search-date-type']:
            set_params.pop(x, None)

        result = None
        predicate_type = 'Within'
        if date_max or search_date_type == 'between':
            #print('Max date provided or implied')
            date_max_final = date_max if date_max else '2009-02-12'
            date_min_final = date_min if date_min else '1609-02-12'
            predicate_type = 'Intersects'
            result ='[%s TO %s]' % (date_min_final, date_max_final)
        else:
            #print('Min date only with %s' % search_date_type)
            result = date_min
            if search_date_type in 'after':
                predicate_type = 'Intersects'
                result = '[%s TO 2009-02-12]' % date_min
            elif search_date_type == 'before':
                predicate_type = 'Intersects'
                result = '[1609-02-12 TO %s]' % date_min
            else:
                result = date_min

        if result:
            fq.append('{!field f=dateRange op=%s}%s' % (predicate_type, result))
    else:
        set_params.pop('search-date-type', None)
    #NB: Advanced search set f1-document-type=letter

    for name in set_params.keys():
        if get_obj_property(name, set_params):
            #print('Processing %s' % name)
            value = set_params[name]

            if name in remap_fields:
                #print('adding %s="%s" to q' % (name,value))
                val_string: str = stringify(value)
                value_final = "(%s)" % val_string
                q.append(":".join([name,value_final]))
                #print(q)
            elif name in ['keyword','text']:
                #print('adding ' + name + ' to q')
                val_string: str = stringify(value)
                value_final = "(%s)" % val_string
                q.append(value_final)
            elif re.match(r'^f[0-9]+-date$', name):
                val_list = value
                val_list.sort()
                fields = ['facet-year', 'facet-year-month', 'facet-year-month-day']
                for date in val_list:
                    date = re.sub(r'^"(.+?)"$', r'\1', date)
                    date_parts = date.split('::')
                    num_parts = len(date_parts)
                    if num_parts == 1:
                        solr_name = 'facet-year'
                    elif num_parts == 2:
                        solr_name = 'facet-year-month'
                    elif num_parts == 3:
                        solr_name = 'facet-year-month-day'
                    contains_nested = fields[num_parts:]
                    contains_parent_or_self = fields[:(num_parts)-1]
                    for index, field in enumerate(fields):
                        if (num_parts-1) <= index:
                            filter['f.%s.facet.contains' % field ] = re.sub(r'^"(.+?)"$', r'\1', date)
                        else:
                            d = "::".join(date_parts[:(index+1)])
                            filter['f.%s.facet.contains' % field ] = re.sub(r'^"(.+?)"$', r'\1', d)
                    fq.append('%s:"%s"' % (solr_name, re.sub(r'^"(.+?)"$', r'\1', date)))
            elif re.match(r'^f[0-9]+-.+?$', name):
                # match old-style xtf facet names f\d+-
                solr_name = re.sub(r'^f[0-9]+-(.+?)$',r'facet-\1', name)
                for x in listify(value):
                    fq.append('%s:"%s"' % (solr_name, re.sub(r'^"(.+?)"$', r'\1', x)))
            elif re.match(r'^(facet|s)-.+?$', name):
                # Add facet params starting facet- or s- (only allowed on site)
                fq.append('%s:"%s"' % (name, re.sub(r'^"(.+?)"$', r'\1', value)))
            elif name == 'page':
                page = int(set_params['page'])
                start = (page - 1) * 20
                solr_params['start'] = start
            elif name == 'sort':
                sort_raw = set_params['sort']
                sort_val: str = ''
                if sort_raw in ['author', 'addressee', 'correspondent', 'date', 'name']:
                    sort_val = 'sort-' + sort_raw
                else:
                    sort_val = 'score'
                sort_order = 'desc' if sort_val == 'score' else 'asc'
                solr_params['sort'] = ' '.join([sort_val, sort_order])
            elif name == 'expand':
                expand_raw = set_params['expand']
                if expand_raw in ['author','addressee', 'correspondent', 'repository', 'volume']:
                    expand_clauses['f.facet-%s.facet.limit' % expand_raw]='-1'
                    expand_clauses['f.facet-%s.facet.sort' % expand_raw]='-1'
            elif name != "rows":
                #print('ELSE adding %s to q with %s' % (name, value))
                val_string: str = stringify(value)
                value_final = "(%s)" % val_string
                q.append(":".join([name,value_final]))

    solr_params['fq'] = fq

    # Hack to ensure that empty q string or * returns all records
    # The whole code that generates the query string will need to be re-examined to deal with this better
    final_q = ' '.join(q)
    if final_q in ["['*']", "['']"]:
        final_q = '*'
    solr_params['q'] = final_q
    if solr_params['q'] in ["['*']", "['']"]:
        solr_params['q'] = '*'
    solr_params = solr_params | filter | expand_clauses
    for i in solr_delete + solr_fields:
        solr_params.pop(i, None)
    #print(resource_type)
    #print('SET PARAMS:')
    #print(set_params)
    #print('FINAL PARAMS:')
    #print(solr_params)
    return solr_params


def generate_datestring(year, month, day):
    result=None
    if year:
        #print(year, month, day)
        # If it's possible to create a valid dateRange token, do so and delete individual date params
        if not (day and not month):
            valid_tokens = [str(i).zfill(2) for i in [year, month, day] if i is not None]
            start_date = '-'.join(valid_tokens)
            result = start_date
        return result


async def delete_resource(resource_type: str, file_id: str):
    delete_query = "fileID:%s" % file_id
    delete_cmd = {'delete': {'query': delete_query}}

    core = get_core_name(resource_type)
    if core:
        r = requests.post(url="%s/solr/%s/update" % (SOLR_URL, core),
                          headers={"content-type": "application/json; charset=UTF-8"},
                          json=delete_cmd,
                          timeout=60)
        status_code = r.status_code
    else:
        status_code = INTERNAL_ERROR_STATUS_CODE

    return status_code


async def get_request(resource_type: str, **kwargs):
    core = get_core_name(resource_type)
    try:
        params = kwargs.copy()
        #print('PARAMS')
        #print(params)
        if 'original_sort' in params:
            del params['original_sort']
        solr_params = translate_params(core, **params)
        #print(solr_params)
        r = requests.get("%s/solr/%s/spell" % (SOLR_URL, core),
                             params=solr_params,
                             headers={"content-type": "application/json; charset=UTF-8"},
                             timeout=60)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        if hasattr(e.response, 'text'):
            results = json.loads(e.response.text)
            raise HTTPException(status_code=results["responseHeader"]["status"], detail=results["error"]["msg"])
        else:
            raise HTTPException(status_code=502, detail=str(e).split(':')[-1])
    result = r.json()
    if 'original_sort' in kwargs and 'sort' in result['responseHeader']['params']:
        result['responseHeader']['params']['sort'] = kwargs["original_sort"]
    return result


async def put_item(resource_type: str, data, params):
    core = get_core_name(resource_type)
    path = 'update/json/docs'
    try:
        r = requests.post(url="%s/solr/%s/%s" % (SOLR_URL, core, path),
                          params=params,
                          headers={"content-type": "application/json; charset=UTF-8"},
                          data=data,
                          timeout=60)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise e
    status_code = r.status_code

    return status_code


# Does FastAPI escape params automatically?
def ensure_urlencoded(var, safe=''):
    if type(var) is str:
        return urllib.parse.quote(urllib.parse.unquote(var, safe))
    elif type(var) is dict:
        dict_new = {}
        for key, value in var.items():
            if value is not None:
                value_final = ''
                if type(value) is str:
                    value_final = urllib.parse.quote(urllib.parse.unquote(value), safe=safe)
                elif type(value) is list:
                    values = []
                    for i in value:
                        values.append(urllib.parse.quote(urllib.parse.unquote(i), safe=safe))
                    value_final = values
                dict_new.update({key: value_final})
        return dict_new


@app.get("/pages")
async def get_pages(request: Request,
                    keyword: List[str] = Query(default=None),
                    s_commentary: Union[str, None] = Query(default=None, alias="s-commentary"),
                    s_key_stage: Union[str, None] = Query(default=None, alias="s-key-stage"),
                    s_ages: Union[str, None] = Query(default=None, alias="s-ages"),
                    s_topics: Union[str, None] = Query(default=None, alias="s-topics"),
                    s_Map_theme: Union[str, None] = Query(default=None, alias="s-Map theme"),
                    facet_searchable: Union[str, None] = Query(default=None, alias="facet-searchable"),
                    sort: Union[str, None] = None,
                    rows: Union[int, None] = None,
                    page: Union[int, None] = 1
                    ):
    q_final = ' '.join(keyword) if hasattr(keyword, '__iter__') else keyword
    rows_final = rows if rows in [10, 20] else 20

    facets = {}
    # Copy facet params into facets array
    # The following is not dealing with them - none of the s_ are passed on.
    for x in request.query_params.keys():
        if re.match(r'^(facet|s)-.+?$', x):
            facets[x]=request.query_params[x]
    if not facet_searchable in ['true','false']:
        facets['facet-searchable'] = 'true'

    params = {"keyword": q_final,
              "sort": sort,
              "page": page,
              "rows": rows_final
              }
    r = await get_request('pages', **params, **facets)
    return r


@app.get("/items")
async def get_items(request: Request,
              sort: Union[str, None] = None,
              page: Union[int, None] = 1,
              rows: Union[int, None] = None,
              expand: Union[str, None] = None,
              keyword: List[str] = Query(default=None),
              text: Union[List[str]| None] = Query(default=None),
              section_type: Union[str, None] = Query(default=None, alias="sectionType"),
              search_author: Union[str, None] = Query(default=None, alias="search-author"),
              search_addressee: Union[str, None] = Query(default=None, alias="search-addressee"),
              search_correspondent: Union[str, None] = Query(default=None, alias="search-correspondent"),
              search_repository: Union[str, None] = Query(default=None, alias="search-repository"),
              exclude_cancelled: Union[str, None] = Query(default=None, alias="exclude-cancelled"),
              exclude_widedate: Union[str, None] = Query(default=None, alias="exclude-widedate"),
              year: Union[int, str, None] = None,
              month: Union[int, str, None] = None,
              day: Union[int, str, None] = None,
              year_max: Union[int, str, None] = Query(default=None, alias="year-max"),
              month_max: Union[int, str, None] = Query(default=None, alias="month-max"),
              day_max: Union[int, str, None] = Query(default=None, alias="day-max"),
              search_date_type: Union[str, None] = Query(default='on', alias="search-date-type")
                    ):
    facets = {}
    #print(request.query_params.keys())
    for x in request.query_params.keys():
        if re.match(r'^f[0-9]+-.+?$', x):
            facets[x]=request.query_params.getlist(x)
    rows_final = rows if rows in [8, 20] else 20

    # Limit params passed through to SOLR
    # Add facet to exclude collections from results
    params = {"sort": sort,
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
              "search-date-type": search_date_type
              }
    r = await get_request('items', **params, **facets)
    return r


@app.get("/json/letters")
async def get_items(q: List[str] = Query(default=None),
              fq: List[str] = Query(default=None)):

    for i in ["facet-document-type:letter", "facet-entry-cancelled:No", "facet-darwin-letter:Yes"]:
        if fq in (None, ""):
            fq = [i]
        else:
            fq.append(i)

    q_final = ' AND '.join(q) if hasattr(q, '__iter__') else q

    # Limit params passed through to SOLR
    # Add facet to exclude collections from results
    params = {"q": q_final, "fq": fq, "sort": "sort-date asc", "rows": 99999, "fl": "id,path,title,date,displayDate,dateStart,direction,deprecated,sender,recipient,url,summary,search-correspondent-id", "hl": "false", "facet.field": ["direction", "facet-document-type"]}
    r = await get_request('items', **params)

    counts = {"To": 0, "From": 0, "3rdParty": 0, "letter": 0, "people": 0, "bibliography": 0}
    dir = r['facet_counts']['facet_fields']['direction']
    type = r['facet_counts']['facet_fields']['facet-document-type']
    facets = dir + type

    for key, value in zip(facets[::2], facets[1::2]):
        counts[key]=value

    output = {
        "requestURI": "/search?f1-document-type=letter&f2-darwin-letter=Yes&f3-entry-cancelled=No&rmode=json&sort=date",
        "dateTimeFormat": "iso8601",
        "statistics": [ {
                "letter": [
                    { "count": counts['letter'],
                      "darwinSent": counts['From'],
                      "darwinReceived": counts['To'],
                      "3rdParty": counts['3rdParty']
                    }
                ] },
            { "people": [ { "count": counts['people'] } ] },
            { "bibliographies": [ { "count": counts['bibliography'] } ] }
        ],
        "letters": r['response']['docs']
        }

    return output

@app.get("/summary")
async def get_summary(q: List[str] = Query(default=None),
                fq: Union[str, None] = None):
    q_final = ' AND '.join(q) if hasattr(q, '__iter__') else q

    # Very few params are relevant to the summary view
    params = {"q": q_final, "fq": fq}

    r = await get_request('items', **params)

    # This query returns the first page of results and the areas of the response that will
    # principally be useful are the responseHeader, response (but not response > docs),
    # facet_counts and possibly highlighting (i.e. snippets).
    # Ultimately, we would change the data structure at this point to the common
    # format needed. Rather than spend time doing  this, I just deleted the docs, which
    # we wouldn't use in this view
    del r['response']['docs']
    return r


# All destructive requests (post, put, delete) will be in a separate API
# that's kept in a private subnet. All access to them would be limited to
# the services that require them (CUDL Indexer - for post, SNS Message on
# deletion of a TEI file in cudl-source-data).
@app.put("/page")
async def update_page(request: Request):
    # Receive data via a data-binary curl request from the CUDL Indexer lambda
    data = await request.body()

    # status_code = ''
    json_dict = json.loads(data)
    if json_dict['facet-document-type'] == 'site':
        logger.info(f"Indexing %s" % json_dict['fileID'])
        status_code = await put_item('page', data, {'f': ['$FQN:/**']})
    else:
        logger.info(f"ERROR: site JSON does not seem to conform to expectations: %s" % json_dict['fileID'])
        # I wasn't sure what status_code to use for invalid document.
        status_code = INTERNAL_ERROR_STATUS_CODE
    return status_code


@app.put("/item")
async def update_item(request: Request):
    # Receive data via a data-binary curl request from the CUDL Indexer lambda
    data = await request.body()

    json_dict = json.loads(data)
    if json_dict['facet-document-type'] in ['letter', 'bibliography', 'people', 'repository', 'documentation']:
        logger.info(f"Indexing %s" % json_dict['fileID'])
        status_code = await put_item('item', data, {'f': ['$FQN:/**', '/*']})
    else:
        logger.info(f"ERROR: item JSON does not seem to conform to expectations: %s" % json_dict['fileID'])
        # I wasn't sure what status_code to use for invalid document.
        status_code = INTERNAL_ERROR_STATUS_CODE
    return status_code


@app.delete("/item/{file_id}")
async def delete_item(file_id: str):
    return await delete_resource('item', file_id)


@app.delete("/page/{file_id}")
async def delete_collection(file_id: str):
    return await delete_resource('page', file_id)
