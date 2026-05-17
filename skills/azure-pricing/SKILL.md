---
name: azure-pricing
description: Fetches real-time Azure retail pricing using the Azure Retail Prices API (prices.azure.com). Use when the user asks about the cost of any Azure service, wants to compare SKU prices, or needs pricing data for a cost estimate. Covers compute, storage, networking, databases, AI, and all other Azure service families.
compatibility: Requires internet access to prices.azure.com. No authentication needed.
metadata:
  author: anthonychu
  version: "3.0"
---

# Azure Pricing Skill

Use this skill to retrieve real-time Azure retail pricing from the public Azure Retail Prices API. No authentication required.

## CRITICAL: How to call http_fetch

NEVER put the filter inside the URL string. ALWAYS pass it as `query_params`.
This is required so the HTTP client encodes it correctly.

Correct call structure:
```json
{
  "method": "GET",
  "url": "https://prices.azure.com/api/retail/prices",
  "query_params": {
    "api-version": "2023-01-01-preview",
    "$filter": "<your filter string here>"
  }
}
```

Wrong (do NOT do this):
```
url: "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&$filter=..."
```

## Step-by-step Instructions

Follow these steps in order. Do not skip any step.

### Step 1 — Resolve the region

Convert the user's region to `armRegionName` format (lowercase, no spaces):

| User says | Use in filter |
|---|---|
| East US | `eastus` |
| West US | `westus` |
| West US 2 | `westus2` |
| West Europe | `westeurope` |
| North Europe | `northeurope` |
| Southeast Asia | `southeastasia` |
| UK South | `uksouth` |
| Australia East | `australiaeast` |
| Central India | `centralindia` |

### Step 2 — Build the filter string

Default to Linux and Consumption unless the user specifies otherwise.

**Linux VM (default):**
```
serviceName eq 'Virtual Machines' and armSkuName eq 'Standard_D4s_v5' and armRegionName eq 'eastus' and priceType eq 'Consumption'
```

**Windows VM:**
```
serviceName eq 'Virtual Machines' and armSkuName eq 'Standard_D4s_v5' and armRegionName eq 'eastus' and priceType eq 'Consumption'
```
Note: Windows and Linux share the same `armSkuName`. After fetching, filter the `Items` array to only items where `meterName` contains `'Windows'` for Windows pricing, or does NOT contain `'Windows'` for Linux pricing.

**Spot pricing:**
```
serviceName eq 'Virtual Machines' and armSkuName eq 'Standard_D4s_v5' and armRegionName eq 'eastus' and contains(meterName, 'Spot')
```

**1-year Reservation:**
```
serviceName eq 'Virtual Machines' and armSkuName eq 'Standard_D4s_v5' and armRegionName eq 'eastus' and priceType eq 'Reservation'
```

Substitute `Standard_D4s_v5` and `eastus` with the actual SKU and region from the user's request.

### Step 3 — Call http_fetch

Use this EXACT structure. Pass `query_params` as a separate dict — never embed the filter in the URL.

Example for Standard_D4s_v5 Linux in East US:
```json
{
  "method": "GET",
  "url": "https://prices.azure.com/api/retail/prices",
  "query_params": {
    "api-version": "2023-01-01-preview",
    "$filter": "serviceName eq 'Virtual Machines' and armSkuName eq 'Standard_D4s_v5' and armRegionName eq 'eastus' and priceType eq 'Consumption'"
  }
}
```

### Step 4 — Parse the response

From the `Items` array in the response:
- Only use items where `isPrimaryMeterRegion` is `true`
- Verify `armRegionName` matches the requested region exactly
- Verify `armSkuName` matches the requested SKU exactly
- **Linux pricing**: use items where `meterName` does NOT contain `Windows`
- **Windows pricing**: use items where `meterName` CONTAINS `Windows`

The same API call returns both Linux and Windows meters — you distinguish them purely by `meterName`.

Extract from the matching item:
| Field | Use for |
|---|---|
| `retailPrice` | unit_price in cost_estimator |
| `unitOfMeasure` | unit_of_measure in cost_estimator |
| `skuName` | label in cost_estimator |
| `meterName` | confirm pricing type |

If no items match after filtering, try broadening — remove `priceType` from the filter and retry.

### Step 5 — ALWAYS call cost_estimator immediately

Do NOT ask the user for usage hours. Default to 730 hours/month (24/7).

```json
{
  "unit_price": <retailPrice from Step 4>,
  "unit_of_measure": "1 Hour",
  "quantity": 730,
  "label": "Standard_D4s_v5 - East US - Linux - On-Demand"
}
```

### Step 6 — Present results

Show in this order:
1. Hourly price
2. Monthly estimate (730 hrs)
3. Annual estimate
4. OS and pricing tier used
5. Offer to also fetch Spot or Reservation pricing if the user wants a cheaper option

## Tips

- `serviceName` is case-sensitive. Use `'Virtual Machines'` not `'virtual machines'`.
- If results are empty, remove `priceType` from the filter first and retry.
- Prices are always in USD.
- Never guess or estimate prices — always fetch from the API.