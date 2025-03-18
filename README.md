# Darwin Search API

The Darwin Search API is based on [CUDL Search](https://github.com/cambridge-collection/cudl-search).

For the Darwin release, use the `darwin-main` branch; the `main` branch contains the original CUDL Search code.

## Prerequisites

- **Docker:** Make sure Docker is installed.
- **Environment Variables:** Set the following environment variables either in your shell or via a `.env` file:
    - `SOLR_HOST`
    - `SOLR_PORT`
    - `API_PORT`

Example `.env` file:

```env
SOLR_HOST=localhost
SOLR_PORT=8983
API_PORT=90
```

## Running Locally

To run the API locally, use the following command:

```bash
docker compose --env-file .env up --build --force-recreate
```

## Accessing the API

The API will be available on the port defined in `API_PORT`. For example:

- If `API_PORT` is set to `90`, access the API at: 
  <http://localhost:90/items?keyword=*>

- If `API_PORT` is set to `80`, access the API at: 
  <http://localhost/items?keyword=*>

## API Endpoints

### TEI Documents

- **Search TEI Items**  
  **GET** `/items`  
  Examples:  
  - <http://localhost/items?keyword=flowers>  
  - <http://localhost/items?text=york&year=1868&exclude-cancelled=Yes&f1-document-type=letter>

- **Index / Remove TEI Item**  
  **PUT** and **DELETE** `/item`

### Site (Drupal) Pages

- **Search Site Pages**  
  **GET** `/pages`  
  Example:  
  - <http://localhost/pages?keyword=flowers>

- **Index / Remove Site Page**  
  **PUT** and **DELETE** `/page`

## PUT and DELETE Operations

These operations are normally triggered by SNS notifications within AWS. For local testing, you can use CURL.

### PUT Requests

For TEI documents:

```bash
curl -X PUT -H "Content-Type: application/json" -d @path/to/TEI-file.json http://localhost/item
```

For HTML website pages:

```bash
curl -X PUT -H "Content-Type: application/json" -d @path/to/drupal-page.json http://localhost/page
```

### DELETE Requests

To delete an item from the index, send a DELETE request with the item's ID:

```bash
curl -X DELETE http://localhost/item/idValue
```

You can find the `id` for an item by performing a search and examining the `id` property in the returned JSON.


## Customising the Solr Search API

The Solr Search API was designed to be extensible, enabling you to add new data models and endpoints or to override the existing one for ‘items’.

### File Structure Overview

The custom code for the Solr Search API is located under the `frontend/custom` directory. A typical structure looks like this:

```
Solr Search API/
├── main.py
└── frontend/
    └── custom/
        ├── __init__.py
        ├── config.py                # Centralised configuration and constants
        ├── implementation.py        # Aggregates routers from the 
        |                            # models subdirectory and re-
        |                            # exports shared models/logic
        └── models/
            ├── __init__.py
            ├── site_pages.py        # Models & endpoints for 
            |                        # website pages
            └── your_stuff.py        # Your models & endpoints
```

### Set Defaults in `config.py`

The following parameters must be defined in `config.py`.

`DEFAULT_ROWS` contains the number of entries retrieved per page of results

CORE_MAP maps the resource’s name to its Solr Core.

```
CORE_MAP = {
    # resource name -> solr core name
    "item": "dcp",
    "page": "site",
}
```

### How to add a New Data Model and Endpoints

This example assumes that you want to support a new resource called ‘collections’.

1. **Create a New Module**

   In the `frontend/custom/models` directory, create a new file called `collections.py`. This file should define the Pydantic V2 models and its FastAPI endpoints.

   By default, the Solr Search API makes the following presumptions about parameters:
    1. you do not redefine or attempt to use the names of the core parameters used by all models (`keyword`, `sort`, `rows`, `page`)
    2. all facet parameters will be preceded by `facet-` (*e.g.*) `facet-document-type`. These will be translated into a Solr facet query.
    2. All other parameters are treated as field names and will be translated into a Solr Query. The parameter `author` would search the `author` field defined in your Solr schema.

   For example:

   ```python
   from fastapi import APIRouter
   from pydantic import BaseModel
   import frontend.lib.utils as utils

   router = APIRouter()

   # All models should be based on CoreQueryParams. It defines the 
   # parameters and functionality common to all endpoints
   class Collection(CoreQueryParams):
       id: int
       name: str
       # Add additional fields as needed.
       
       # You can also add custom model and field validators
       # that run before or after the core processing.
       # If the mapping of your API's parameters to Solr
       # fieldnames isn't a one to one correspondence, 
       # you will need to add a get_solr_params function
       # into the model 

   @router.get("/collections", response_model=list[Collection])
   def get_collections():
       # All logic concerning the parsing, validation and manipulation
       # of paramters and their values should be done in the Collection 
       # model.
       # The following two commands are all that's needed to convert
       # your parameters into solr queries and retrieve the request.

       solr_params = params.get_solr_params()
       return await utils.get_request("pages", **solr_params)

   @router.put("/collections")
   def create_collection(request: Request):
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
      # delete_resource takes two parameters. The first is the
      # core name (defined in your custom implementation
      # the unique id value of your resource
	    return await utils.delete_resource("page", file_id)

   ```

2. **Register the Router for your endpoints**

   Import your new router into `frontend/custom/implementation.py` and then include it in the aggregated router. It will then be automatically available to the search API.

   Example modification to `implementation.py`:

   ```python
   from fastapi import APIRouter
   from frontend.custom.models.site_pages import router as pages_router
   
   # Import your router
   from frontend.custom.models.collections import router as collections_router

   router = APIRouter()

   router.include_router(pages_router)
   
   # Register your collection endpoints
   router.include_router(collections_router)
   ```

### Default Endpoints for Items

If no custom implementation is provided for `ItemsQueryParams` and its endpoints, the Solr Search API will fall back to using the default ones defined in the main application.New projects likely will not need a custom model. The chief reasons to add one would be to support special any special validation and processing requirements that you might have for your parameter values. of certain parameter values. Legacy projects, however, will likely require rather extensive models the url parameters of their legacy applications.
