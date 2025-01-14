# Darwin Search API

This repository is based off [CUDL Search](https://github.com/cambridge-collection/cudl-search).

## Prerequisites

1. Docker installed
2. `SOLR_HOST`, `SOLR_PORT` and `API_PORT` environment variables set in shell or in `.env` file.

## Running locally

    docker compose --env-file .env up --build --force-recreate

## Accessing the API

The API will be available on port defined in `API_PORT`. If set to 90, it would be available at <http://localhost:90/items?keyword=*>.If set to 80, it would be available at <http://localhost/items?keyword=*>

The API defines the following endpoints:

TEI documents

- `/items` [`GET`] for searching, _e.g._ <http://localhost/items?keyword=flowers> or <http://localhost/items?text=york&year=1868&exclude-cancelled=Yes&f1-document-type=letter>
- `/item` [`PUT`, `DELETE`] - for submitting a TEI item for indexing or for removing it from the index

Site (Drupal) Pages

- `/pages` [`GET`] for searching <http://localhost/pages?keyword=flowers>
- `/page` [`PUT`, `DELETE`] - for submitting a drupal page for indexing or for removing it from the index

### `PUT` and `DELETE` 

`PUT` and `DELETE` actions are triggered with SNS notifications within AWS. On a local development server, they can be triggered using CURL.

#### PUT

`curl -X PUT -H "Content-Type: application/json" -d @path/to/TEI-file.json http://localhost/item` (for TEI)

`curl -X PUT -H "Content-Type: application/json" -d @path/to/drupal-page.json http://localhost/page` (for a website page)

#### DELETE

To delete an item from the index, you a delete request is submitted with the item's id value:

`http://localhost/item/idValue`

You can find the `id` for an item by performing a search for it and examining the `id` property in the returned JSON.
