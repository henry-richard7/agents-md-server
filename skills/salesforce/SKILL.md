---
name: salesforce
description: Read-only querying and inspection of Salesforce CRM data (Accounts, Contacts, Leads, Opportunities, and Custom Objects) via the Salesforce REST API. Supports SOQL queries, automatic multi-page pagination (nextRecordsUrl), record retrieval by ID, and schema inspection (describe).
compatibility: Requires internet access to your Salesforce instance. Authentication required via OAuth2 or Bearer token.
metadata:
  author: Henry-Richard
  version: "1.1"
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

Choose the authentication mode configured in your environment:

### Option A: OAuth 2.0 Client Credentials (Recommended)
- **`auth_type`**: `"client_credentials"`
- **`env_client_id`**: `"SALESFORCE_CLIENT_ID"`
- **`env_client_secret`**: `"SALESFORCE_CLIENT_SECRET"`
- **`token_url`**: `"${SALESFORCE_INSTANCE_URL}/services/oauth2/token"`
- **Base URL**: `${SALESFORCE_INSTANCE_URL}`

### Option B: Direct Bearer Token
- **`auth_type`**: `"bearer"`
- **`env_key`**: `"SALESFORCE_TOKEN"`
- **Base URL**: `${SALESFORCE_INSTANCE_URL}`

---

## CRITICAL: SOQL Query & Pagination Rules

### Rule 1: DO NOT artificially limit queries
- **Never append `LIMIT 10` or `LIMIT 20` unless the user explicitly requested a small limit** (e.g., *"give me top 5 accounts"*).
- When asked to list, search, or summarize records (e.g. *"list all opportunities in Stage 'Closed Won'"* or *"find accounts in New York"*), write the full query **without a `LIMIT` clause**.

### Rule 2: Always inspect `"done"` and paginate with `nextRecordsUrl`
Salesforce returns records in batches (up to 2,000 records per page).
1. When you execute a query, check the response:
   - If `"done": true`: you have all the records.
   - If `"done": false`: there are more records. Notice the `"nextRecordsUrl"` field in the response (e.g., `"/services/data/v60.0/query/01gD0000002HU6iIAG-2000"`).
2. **You MUST fetch the next page** by making a follow-up call:
   - Call `auth_http_fetch` with `url="${SALESFORCE_INSTANCE_URL}" + response["nextRecordsUrl"]`.
   - Do **NOT** pass `q` or `query_params` when fetching `nextRecordsUrl`. The query ID is already in the URL path.
   - Repeat this until `"done": true`, or until you have gathered all records needed to answer the user's question.

---

## 1. Execute SOQL Query & Pagination Example

### Step 1: Initial Query
- **Method**: `GET`
- **URL**: `${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query`
- **Query Params**: Pass `q` inside `query_params` with your complete SOQL query (do not add `LIMIT` unless requested).

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "${SALESFORCE_INSTANCE_URL}/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query",
  "query_params": {
    "q": "SELECT Id, Name, StageName, Amount, CloseDate, Account.Name FROM Opportunity WHERE IsClosed = false"
  }
}
```

### Step 2: Next Page Call (When `done: false`)
If the initial response has `"done": false` and `"nextRecordsUrl": "/services/data/v60.0/query/01gD0000002HU6iIAG-2000"`, make the follow-up call immediately:

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "${SALESFORCE_INSTANCE_URL}/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query/01gD0000002HU6iIAG-2000"
}
```

### Common SOQL Patterns
- **Accounts:**
  `SELECT Id, Name, Type, Industry, BillingCity, AnnualRevenue FROM Account ORDER BY Name ASC`
- **Contacts:**
  `SELECT Id, FirstName, LastName, Email, Title, Account.Name FROM Contact WHERE Email != null`
- **Opportunities:**
  `SELECT Id, Name, StageName, Amount, CloseDate, Account.Name FROM Opportunity WHERE IsClosed = false`
- **Leads:**
  `SELECT Id, Name, Company, Status, Email, LeadSource FROM Lead WHERE Status != 'Closed - Converted'`
- **Custom Objects:**
  `SELECT Id, Name, Custom_Field__c FROM My_Custom_Object__c`

### Controlling Page Size (Optional)
If you want smaller page batches (e.g. 100 or 200 records per page), pass the `Sforce-Query-Options` header:
```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "${SALESFORCE_INSTANCE_URL}/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/query",
  "query_params": {
    "q": "SELECT Id, Name FROM Account"
  },
  "extra_headers": {
    "Sforce-Query-Options": "batchSize=200"
  }
}
```

---

## 2. Inspect Object Schema (Describe)

Inspect schema to see all available field names, types, relationships, and picklist values.

- **Method**: `GET`
- **URL**: `${SALESFORCE_INSTANCE_URL}/services/data/v60.0/sobjects/{sObject}/describe`
- Replace `{sObject}` with `Account`, `Contact`, `Lead`, `Opportunity`, or custom object `My_Object__c`.

```json
{
  "auth_type": "client_credentials",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "token_url": "${SALESFORCE_INSTANCE_URL}/services/oauth2/token",
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
  "token_url": "${SALESFORCE_INSTANCE_URL}/services/oauth2/token",
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
  "token_url": "${SALESFORCE_INSTANCE_URL}/services/oauth2/token",
  "method": "GET",
  "url": "${SALESFORCE_INSTANCE_URL}/services/data/v60.0/limits"
}
```
