---
name: databricks
description: Fetches databricks endpoints using the Databricks REST API.
compatibility: Requires internet access to databricks.com. Authentication required.
metadata:
  author: Henry-Richard
  version: "1.0"
---

# Databricks skill
Use this skill to fetch databricks endpoints and any questions related to databricks.

# Databricks Jobs
## List all jobs
Follow the below steps to list all jobs in a workspace:
Step 1: call auth_http_fetch
use `auth_type="bearer"` and pass `env_key="DATABRICKS_TOKEN"`.
use `method="GET"`
use `url="${DATABRICKS_HOST}/api/2.2/jobs/list"`

```json
{
  "auth_type": "bearer",
  "env_key": "DATABRICKS_TOKEN",
  "method": "GET",
  "url": "${DATABRICKS_HOST}/api/2.2/jobs/list"
}
```
## Get a single job

This need to use the tool `auth_http_fetch`
use `auth_type="bearer"` and pass `env_key="DATABRICKS_TOKEN"`.
use `method="GET"`
use `url="${DATABRICKS_HOST}/api/2.2/jobs/get"`

Retrieves the details for a single job.

Large arrays in the results will be paginated when they exceed 100 elements. A request for a single job will return all properties for that job, and the first 100 elements of array properties (tasks, job_clusters, environments and parameters). Use the next_page_token field to check for more results and pass its value as the page_token in subsequent requests. If any array properties have more than 100 elements, additional results will be returned on subsequent requests. Arrays without additional results will be empty on later pages.

## Query parameters

- `job_id` (int64, required, ID, Immutable)
  The canonical identifier of the job to retrieve information about. This field is required.
  Example: `11223344`
- `include_trigger_state` (boolean, optional)
  Flag that indicates that trigger state should be included in the response.
  Default: `false`
- `page_token` (string, optional)
  Use `next_page_token` returned from the previous GetJob response to request the next page of the job's array properties.
  Example: `CAAos-uriYcxMN7_rt_v7B4=`