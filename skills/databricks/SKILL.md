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

