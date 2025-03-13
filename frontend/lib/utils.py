#!/usr/bin/env python3
from typing import Union, List

def stringify(p: Union[List, any]) -> str:
    if isinstance(p, list):
        return " ".join(map(str, p))
    return str(p)

def listify(p: any) -> List:
    return p if isinstance(p, list) else [p]

def ensure_urlencoded(var, safe=""):
    if isinstance(var, str):
        return urllib.parse.quote(urllib.parse.unquote(var), safe=safe)
    elif isinstance(var, dict):
        return {k: ensure_urlencoded(v, safe) for k, v in var.items() if v is not None}
    elif isinstance(var, list):
        return [ensure_urlencoded(item, safe) for item in var]
    return var
