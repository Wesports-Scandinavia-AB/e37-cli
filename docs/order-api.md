# E37 Order API Reference

*Integration notes for `e37-cli`*

Everything we currently know about pulling order data out of the E37 webshop platform: the new order flow report, the existing Triton Admin REST API, and the status webhook. Compiled from E37's public documentation and the report UI.

| | |
|---|---|
| Compiled | 3 September 2026 |
| Platform | E37 Triton Admin 1.0 |
| Vendor contact | support@e37.se |

## Status

Nothing in this document has been exercised against a live endpoint yet: it is built from E37's public OpenAPI spec and the report UI. Items marked **[unverified]** are inferred and need a real call or a confirmation from E37. When `e37-cli` gets a live response that disagrees, this document is wrong and gets fixed.

## Two APIs, one key

E37 exposes order data through two separate mechanisms that share the same API key but authenticate differently.

| Mechanism | Purpose | Auth | Format |
|---|---|---|---|
| **Order flow report** `/api/reports/orderflow` | Lightweight list of orders completed in a time window. Built for polling, monitoring and dashboards. | API key as `key` query parameter | JSON (also table and file downloads from the UI) |
| **Triton Admin REST API** `/api/orders/{id}` and friends | Full detail for one order: customer, addresses, payment, delivery, rows. Also marketplace order creation and gift cards. | HTTP Basic: webshop ID as username, API key as password | JSON |
| **Order status webhook** | Push notification when an order's status changes, with tracking data. | Registered in E37 Admin (outbound from E37) | JSON POST to our URL |

E37 recommends combining the first two: poll the report for new order numbers, then call the REST API per order for the details the report does not carry.

## Authentication

### Creating the key

The OpenAPI spec says only that a key is created "in your webshop's back-end", meaning E37 Admin at <https://admin3.e37.se>. The exact menu location is not documented in E37's public help centre.

Treat the key as a password. Store it in a secret store or environment variable, never in a script, ticket or chat.

### Report endpoint: query parameter

```
GET https://admin3.e37.se/api/reports/orderflow?account=<account>&key=<API KEY>&...
```

The key travels in the URL. Over HTTPS it is encrypted in transit, but it will land in E37's web server logs, Cloudflare logs, browser history and anywhere the URL is pasted. Keep the key out of shared documents and mask it in our own logs.

### REST API: HTTP Basic

Username is the webshop ID, password is the API key, base64-encoded together.

```
Authorization: Basic base64(<WEBSHOP ID>:<API KEY>)
```

> **Recommendation to raise with E37.** Since the REST API already accepts the key in an Authorization header, ask E37 to let the report endpoint accept the same Basic auth, keeping the query parameter only for link-based tools such as Excel or Power BI. This is a small change on their side and removes the key from URL logs.

## Order flow report

Announced by E37 on 27 August 2026 as the "orderflödesrapport". It is a report in E37 Admin that also has a URL for automated calls. In the UI it lives under **E-handel → Rapporter**, report type **Orderrapport – orderflödesrapport**. The button **Skapa länk till rapport** shows the URL for the current settings.

### Request

Example URL exactly as E37's screenshot shows it, with the key placeholder:

```
https://admin3.e37.se/api/reports/orderflow
  ?account=<account>
  &key=<INSERT API KEY>
  &dateInterval=2026-08-26+18%3a30%2c2026-08-26+19%3a30
  &orderTimestampMode=completed
```

| Parameter | Value | Notes |
|---|---|---|
| `account` | Shop account slug, e.g. `<account>` | One E37 account can host several sites (shop-in-shop). Whether one key covers all accounts is **[unverified]**. |
| `key` | API key | Created in E37 Admin. |
| `dateInterval` | `YYYY-MM-DD HH:MM,YYYY-MM-DD HH:MM` | Start and end separated by a comma. URL-encoded: space becomes `+`, colon `%3a`, comma `%2c`. Inclusive/exclusive boundaries are **[unverified]**. |
| `orderTimestampMode` | `completed` | Filter on the time the payment provider confirmed the order (Klarna, Svea callback etc.), not the creation time. This is what makes gap-free polling possible. Other values presumably exist for creation time; **[unverified]**. |

The UI also offers filters for order status, excluded order status and site, plus a file type selector (Json shown). Whether these appear as extra query parameters when included in the generated link is **[unverified]**. Generate a link with them set and compare.

### Response, minimal column set

A JSON object with a `rows` array. Each row:

| Field | Example | Meaning |
|---|---|---|
| `order_id` | `1189437` | E37 order number. Use it for `GET /orders/{id}`. |
| `order_timestamp` | `2026-08-26T18:30:13` | Order time. No timezone offset in the string; almost certainly Europe/Stockholm local time **[unverified]**. Fractional seconds appear on some rows (`18:35:00.75`). |
| `total_sum_excl_vat` | `862.4000` | Order total excluding VAT, four decimals. |
| `total_sum_incl_vat` | `1078.0000` | Order total including VAT. |
| `currency` | `SEK` | Also seen: NOK, DKK. |
| `country` | `SE` | ISO country code. |
| `country_name` | `Sverige` | Localised country name. |
| `language` | `SV` | Also seen: NO, DA. |
| `person_type` | `Privatperson` | Customer type as text. Company orders presumably differ; **[unverified]**. |
| `site_id` | `4` | Site (shop-in-shop) numeric ID. See [Known shops and sites](#known-shops-and-sites). |
| `site_name` | `Example Shop SE` | Site display name. |

Example:

```json
{
  "rows": [
    {
      "order_id": 1189437,
      "order_timestamp": "2026-08-26T18:30:13",
      "total_sum_excl_vat": 862.4000,
      "total_sum_incl_vat": 1078.0000,
      "currency": "SEK",
      "country": "SE",
      "country_name": "Sverige",
      "language": "SV",
      "person_type": "Privatperson",
      "site_id": 4,
      "site_name": "Example Shop SE"
    }
  ]
}
```

### Optional extra columns

Tick these in the report UI before generating the link. Exact JSON field names are **[unverified]** until we see a response.

- Customer number and basic customer details
- Amount paid with gift card and remaining amount to pay
- Shipping cost
- Order status
- Other status: Garp (Spobik) ERP sync status and any order error code
- Payment method
- External marketplace

## Polling recipe

E37's recommended cadence: fetch every 30 minutes, two minutes after the half hour, always asking for the previous closed half-hour window. Because the filter is on completion time, orders that were created earlier but paid late fall into the window in which they were actually completed, so nothing is missed and nothing is fetched twice.

| Run at | Fetch window |
|---|---|
| 14:02 | 13:30 – 14:00 |
| 14:32 | 14:00 – 14:30 |
| 15:02 | 14:30 – 15:00 |
| 15:32 | 15:00 – 15:30 |

Practical additions on our side:

- Persist the last successfully fetched window end. On failure, retry the same window rather than skipping ahead.
- Upsert on `order_id` so a re-run of a window is harmless.
- Run the schedule in Europe/Stockholm time until E37 confirms the timestamp timezone.
- Alert when a shop returns zero rows during trading hours for longer than expected. This is the monitoring use case E37 had in mind.

### First manual call

PowerShell, with the key in an environment variable:

```powershell
$env:E37_KEY = "paste-key-here"
$from = "2026-09-02+08%3a00"
$to   = "2026-09-02+08%3a30"
curl.exe "https://admin3.e37.se/api/reports/orderflow?account=<account>&key=$env:E37_KEY&dateInterval=$from%2c$to&orderTimestampMode=completed"
```

Bash:

```bash
export E37_KEY="paste-key-here"
curl -s "https://admin3.e37.se/api/reports/orderflow?account=<account>&key=${E37_KEY}&dateInterval=2026-09-02+08%3a00%2c2026-09-02+08%3a30&orderTimestampMode=completed" | jq '.rows | length'
```

## Triton Admin REST API

Source: OpenAPI 3 spec "Triton Admin 1.0", published at <https://admin3.e37.se/docs/>. Rendered with Stoplight.

### Base URLs

| Server | Base URL |
|---|---|
| web02 | `https://admin2.e37.se/api` |
| web03 | `https://admin3.e37.se/api` |

Each webshop lives on one of these servers. Confirm per shop; `e37-cli` defaults to admin3.

### `GET /orders/{id}`

Returns full information about one order. Path parameter `id` is the E37 order number (integer). Responses: 200 with an `Order` object, 404 if not found.

```bash
curl -u "<WEBSHOP ID>:<API KEY>" https://admin3.e37.se/api/orders/1189437
```

#### Order object

| Field | Type | Description |
|---|---|---|
| `id` | integer | E37 order number |
| `timestamp` | date-time | When the order was created (e.g. `2022-01-14T12:07:39.827`, no offset) |
| `synced` | boolean | Whether the order has been synced to the ERP |
| `erpOrderNumber` | string | Order number in the ERP, null until synced |
| `languageCode` | string | e.g. `sv` |
| `currencyCode` | string | e.g. `sek` |
| `externalOrder` | object | For marketplace orders: `source.id`, `source.name`, `externalOrderNumber`, `timestamp` |
| `site` | object | `id` (string) and `name` of the site the order was placed on |
| `orderStatus` | object | `id` (e.g. `NEWORDER`) and `name` |
| `customer` | object | `customerNumber`, `type` (1 individual, 2 company), `newCustomer`, `acceptsMarketing`, `email`, `phone`, `mobilePhone`, `invoiceAddress`, `deliveryAddress`. Addresses have `name`, `address1`, `address2`, `zipCode`, `city`, `countryCode`. |
| `payment` | object | `paymentMethod` (e.g. "Klarna Checkout V3"), `reference`, `status` (ACTIVATED, CANCELLED, NOT_ACTIVATED), `feeExclVat`, `feeInclVat`, `feeVatAmount` |
| `delivery` | object | `deliveryMethod`, fee fields, `deliveryDate`, `pickupDate`, `tms` (`sent`, `sentTimestamp`, `serviceID`) |
| `pickupLocation` | object | `id`, `type` (0 none, 1 transport company, 2 matrix, 3 location, 4 reseller, 5 time slot), `name`, `address`, `zipCode`, `city` |
| `ipAddress` | string | Customer IP |
| `message` | string | Message from customer |
| `totalSumInclVat`, `totalSumExclVat`, `vatSum` | number | Order totals |
| `totalWeight` | number | Total weight (grams in the example) |
| `rows` | array | Order rows, see below |

#### Order row

| Field | Description |
|---|---|
| `id` | Order row ID |
| `sku`, `supplierSKU`, `manufacturerSKU` | Product identifiers |
| `name` / `title` | Product name. The schema says `name`, the example says `title`. Expect either; **[unverified]**. |
| `variant` / `matrices` | Variant text, e.g. "Grön, Medium". Same schema-versus-example mismatch as above. |
| `brand` / `trademark` | Brand, e.g. "Scott". Same mismatch. |
| `quantity`, `unit`, `weight` | Quantity, unit ("st"), weight per unit |
| `vatPercentage` | VAT rate, e.g. 25 |
| `priceInclVat`, `priceExclVat` | Unit price actually paid |
| `sumInclVat`, `sumExclVat` | Row totals actually paid |
| `regularPriceInclVat`, `regularPriceExclVat`, `regularSumInclVat`, `regularSumExclVat` | Undiscounted price and sums. Discount per row is the difference. |
| `inStock`, `stockInfo` | Stock state at order time |
| `returnQuantityAccepted`, `returnQuantityPending` | Returns |
| `isPackageRoot`, `subRows` | Bundle structure |
| `additionalInfo`, `attachment` | Free text and file attachment |

Note what is **not** in the Order object: discount or campaign rows as separate lines, status history, and delivery promise. They have to come from E37 directly or from the status webhook over time.

### `GET /orders/{id}/status`

Returns only the current status. Response: `ID`, `ExternalOrderNumber`, and `OrderStatus` with numeric `ID` and `Name`.

| ID | Status |
|---:|---|
| 1 | NewOrder |
| 2 | Cancelled |
| 3 | Delivered |
| 4 | PackingSlipPrinted |
| 5 | ChangeOrder |
| 6 | PartiallyDelivered |
| -1 | Custom (shop-defined status) |

### `POST /orders/{marketplace_instance_guid}`

Creates a marketplace order in E37 from a `MarketplaceOrder` body. Returns 201 with `E37OrderNumber`, 400 on validation error, 500 on general error. Not needed for the read-only order database but relevant if marketplace integrations are ever consolidated.

### `POST /giftcard`

Creates a gift card from a `GiftCardRequest`, returns a `GiftCardResponse`. Out of scope here.

## Order status webhook

E37 can POST a JSON payload to a URL registered in E37 Admin whenever an order's status changes. Schema name in the spec: `Webhook-OrderStatusChanged`.

```json
{
  "OrderID": 1189437,
  "ExternalOrderNumber": "",
  "ExternalOrderNumberExtra": "",
  "ErpOrderNumber": "",
  "OrderStatus": { "ID": 3, "Type": "Delivered", "Description": "Delivered" },
  "TrackingNumber": "",
  "TrackingURL": ""
}
```

| Field | Description |
|---|---|
| `OrderID` | E37 order number |
| `ExternalOrderNumber` | External order number for marketplace orders |
| `ExternalOrderNumberExtra` | Order number at a marketplace hub such as Sello |
| `ErpOrderNumber` | Order number in the ERP |
| `OrderStatus.ID` | Same numeric codes as the status endpoint |
| `OrderStatus.Type`, `OrderStatus.Description` | Text representations |
| `TrackingNumber`, `TrackingURL` | From the TMS once shipped |

The spec does not describe webhook authentication, signing or retry behaviour. Where in E37 Admin the URL is registered is also undocumented publicly.

## Suggested integration

1. **Poll the order flow report** every 30 minutes per shop account, previous half-hour window, `orderTimestampMode=completed`. Store the rows as the order header table.
2. **Enrich per order** with `GET /orders/{id}` for customer, addresses, payment, delivery and rows. Store rows in an order-lines table keyed on order ID and row ID.
3. **Subscribe to the status webhook** to build status history and capture tracking numbers, instead of polling `/orders/{id}/status`.
4. **Backfill history** through a one-off export from E37. The report endpoint may also accept long date intervals, which would allow a slow self-serve backfill; volume limits are **[unverified]**.
5. **Reconcile** daily by re-fetching the previous day's windows and comparing counts, to catch any window lost to an outage.

## Open questions

1. Where in E37 Admin is the API key created?
2. Is one key valid across all accounts and sites under a webshop ID?
3. Can the report endpoint accept the key via Basic auth header, like the REST API?
4. What timezone are `order_timestamp` and the `dateInterval` filter in? Are interval boundaries inclusive at both ends?
5. Are there rate limits, a maximum interval length or a maximum row count per call?
6. What are the JSON field names for the optional extra columns, and do site and status filters appear as query parameters?
7. What other values does `orderTimestampMode` accept?
8. Where is the status webhook URL registered, and is the payload signed?
9. How is a shop's server, admin2 or admin3, found out other than by trying?

## Sources

- OpenAPI 3 specification "Triton Admin 1.0", <https://admin3.e37.se/docs/Triton-Admin-1.0.json>, rendered at <https://admin3.e37.se/docs/>.
- The order flow report as shown in E37 Admin under **E-handel → Rapporter**.
- E37 help centre, <https://support.e37.se/hc/sv>.
