---
name: salesforce
description: Read-only querying and inspection of Salesforce CRM data (Accounts, Contacts, Leads, Opportunities, and Custom Objects) via the Salesforce REST API. Supports SOQL queries, record retrieval by ID, schema inspection (describe), and pagination. Supports both OAuth2 Client Credentials and Bearer token auth.
compatibility: Requires internet access to your Salesforce instance. Authentication required via OAuth2 or Bearer token.
metadata:
  author: Henry-Richard
  version: "1.0"
  required_env:
    - SALESFORCE_INSTANCE_URL
    - SALESFORCE_CLIENT_ID (if using OAuth2)
    - SALESFORCE_CLIENT_SECRET (if using OAuth2)
    - SALESFORCE_TOKEN (if using direct token)
---

# Salesforce CRM Skill (Read-Only)

Use this skill to query, inspect, and read data from Salesforce CRM using the Salesforce REST API (v60.0).

> **Policy:** This skill is strictly **READ-ONLY**. Do NOT attempt to create, update, or delete records. Only `GET` requests are permitted. If a user asks to modify data, politely inform them that this integration is configured for read-only access.

---

## Authentication Options

Salesforce supports two authentication modes with `auth_http_fetch`. Choose the one configured in your environment:

### Option A: OAuth 2.0 Client Credentials (Recommended for Connected Apps)

Use this when connecting via a Salesforce Connected App or External Client App. Skilldeck automatically fetches and caches access tokens from Salesforce's OAuth endpoint and handles token refreshes:

- **`auth_type`**: `"client_credentials"`
- **`env_client_id`**: `"SALESFORCE_CLIENT_ID"` (Consumer Key from Connected App)
- **`env_client_secret`**: `"SALESFORCE_CLIENT_SECRET"` (Consumer Secret)
- **`token_url`**: `"https://login.salesforce.com/services/oauth2/token"` (or `"https://test.salesforce.com/services/oauth2/token"` for sandboxes)
- **Base URL**: `${SALESFORCE_INSTANCE_URL}`

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "https://login.salesforce.com/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query",
  "query_params": {
    "q": "SELECT Id, Name, Industry FROM Account LIMIT 10"
  }
}
```

### Option B: Direct Bearer Token (Quick Testing / Personal Access)

Use this if you already have a temporary access token or session ID:

- **`auth_type`**: `"bearer"`
- **`env_key`**: `"SALESFORCE_TOKEN"`
- **Base URL**: `${SALESFORCE_INSTANCE_URL}`

```json
{
  "auth_type": "bearer",
  "env_key": "SALESFORCE_TOKEN",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query",
  "query_params": {
    "q": "SELECT Id, Name, Industry FROM Account LIMIT 10"
  }
}
```

> **Note:** Never pass raw secrets directly in prompts or tool calls. Always pass variable names like `env_client_id="SALESFORCE_CLIENT_ID"` or `env_key="SALESFORCE_TOKEN"` so secrets remain protected in `.env`.

---

## 1. Execute SOQL Query (Search & Read)

Use SOQL (Salesforce Object Query Language) to retrieve records with filters, sorting, and limits.

### How to Call `auth_http_fetch`
- **Method**: `GET`
- **URL**: `${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query`
- **Query Params**: Pass `q` inside `query_params` (do **not** put raw SOQL directly in the URL string).

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "https://login.salesforce.com/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query",
  "query_params": {
    "q": "SELECT Id, Name, Industry, AnnualRevenue, Phone FROM Account ORDER BY CreatedDate DESC LIMIT 20"
  }
}
```

### Common SOQL Patterns
- **Find Accounts by name/industry:**
  `SELECT Id, Name, Type, Industry, BillingCity FROM Account WHERE Name LIKE '%Acme%' LIMIT 10`
- **Find Contacts by email/account:**
  `SELECT Id, FirstName, LastName, Email, Title, Account.Name FROM Contact WHERE Email = 'john@example.com'`
- **Find Open Opportunities:**
  `SELECT Id, Name, StageName, Amount, CloseDate, Account.Name FROM Opportunity WHERE IsClosed = false ORDER BY Amount DESC LIMIT 25`
- **Find Recent Leads:**
  `SELECT Id, Name, Company, Status, Email, LeadSource FROM Lead WHERE Status != 'Closed - Converted' ORDER BY CreatedDate DESC LIMIT 20`

### Handling Pagination (`nextRecordsUrl`)
When a query has more records than the batch size, the response contains:
- `"done": false`
- `"nextRecordsUrl": "/services/data/v60.0/query/01gD0000002HU6iIAG-2000"`

To fetch the next page, call `auth_http_fetch` with:
- **URL**: `${SALESFORCE_INSTANCE_URL}{nextRecordsUrl}`
- **Method**: `GET`

---

## 2. Inspect Object Schema (Describe)

Inspect the schema to see available field names, types, relationships, and picklist values.

- **Method**: `GET`
- **URL**: `${SALESFORCE_INSTANCE_URL}/services/data/v60.0/sobjects/{sObject}/describe`
- Replace `{sObject}` with `Account`, `Contact`, `Lead`, `Opportunity`, or custom object `My_Object__c`.

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "https://login.salesforce.com/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/sobjects/Account/describe"
}
```

---

## 3. Get Single Record by ID

Retrieve all or specific fields of a single record using its 15 or 18 character Salesforce ID.

- **Method**: `GET`
- **URL**: `${SALESFORCE_INSTANCE_URL}/services/data/v60.0/sobjects/{sObject}/{id}`

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "https://login.salesforce.com/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/sobjects/Contact/003D000000QV4IsIAL"
}
```

---

## 4. Check API Limits

Check remaining daily REST API calls and governor limits for the Salesforce org.

- **Method**: `GET`
- **URL**: `${SALESFORCE_INSTANCE_URL}/services/data/v60.0/limits`

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "https://login.salesforce.com/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/limits"
}
```
