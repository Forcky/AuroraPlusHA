# Aurora Energy Tasmania (Aurora+) — Unofficial API Reference

This document captures everything discovered about the Aurora Energy Tasmania REST API through reverse engineering the Aurora+ web portal. It is intended to help the community build on this work.

> **Disclaimer:** This is an unofficial, undocumented API. Aurora Energy may change it at any time without notice. Use at your own risk.

---

## Base URL

```
https://api.auroraenergy.com.au/api
```

---

## Authentication

Aurora+ uses a two-stage authentication flow:

1. Azure B2C OIDC (produces an `id_token`)
2. Aurora proprietary token exchange (produces a bearer `access_token` + refresh mechanism)

### Stage 1 — Azure B2C Login (manual step)

The `id_token` is obtained by logging into the Aurora+ web portal via Azure B2C:

- **Portal URL:** `https://my.auroraenergy.com.au`
- **OAuth2 PKCE flow:**
  - **Authorize URL:** `https://customers.auroraenergy.com.au/auroracustomers1p.onmicrosoft.com/b2c_1a_sign_in/oauth2/v2.0/authorize`
  - **Token URL:** `https://customers.auroraenergy.com.au/auroracustomers1p.onmicrosoft.com/b2c_1a_sign_in/oauth2/v2.0/token`
  - **Client ID:** `2ff9da64-8629-4a92-a4b6-850a3f02053d`
  - **Redirect URI:** `https://my.auroraenergy.com.au/login/redirect`
  - **Scopes:** `openid profile offline_access`

The `id_token` is a JWT (starts with `eyJ...`) and is **short-lived** (expires within a few minutes). It must be exchanged immediately.

> **Tip:** Tick **"Keep me logged in"** at login — this is required for the refresh token to remain valid long-term.

---

### Stage 2 — Token Exchange

#### `POST /api/identity/LoginToken`

Exchanges the Azure B2C `id_token` for an Aurora bearer `access_token`.

**Request headers:**
```
Content-Type: application/json
Accept: application/json
User-Agent: python/auroraplus
```

**Request body:**
```json
{
  "token": "<azure_b2c_id_token>"
}
```

**Response (200):**
```json
{
  "tokenType": "bearer",
  "accessToken": "bearer eyJ...<jwt>",
  "refreshToken": "<opaque_refresh_token>"
}
```

**Key notes:**
- The `accessToken` value includes the `"bearer "` prefix — **strip it** before use: `token.split(" ")[1]` or `token.removeprefix("bearer ")`
- A `RefreshToken` cookie is also set in the response — store this alongside the refresh token for later refresh calls
- A 401/403 response means the `id_token` was rejected (expired or invalid)

---

### Token Refresh

#### `POST /api/identity/refreshToken`

Obtains a new `access_token` using the stored refresh token and cookie.

**Request headers:**
```
Content-Type: application/json
Accept: application/json
User-Agent: python/auroraplus
```

**Request body:**
```json
{
  "token": "<refresh_token>"
}
```

**Request cookie:**
```
RefreshToken=<refresh_cookie_value>
```

**Response (200):** Same structure as `/LoginToken`

**Notes:**
- A 401/403 response means the refresh token has expired — full re-authentication required
- The response may include an updated `refreshToken` — always store the latest value
- The `RefreshToken` cookie in the response may also be updated — store the latest value

---

### Using the access token

All API calls require the bearer token in the `Authorization` header. The following headers should be sent with every request:

```
Authorization: Bearer <access_token>
Accept: application/json
User-Agent: python/auroraplus
```

> **Important:** Omitting `Accept: application/json` causes the usage endpoint to return null values for all metered records, even when data exists. Always include this header.

---

## Endpoints

### `GET /api/customers/current`

Returns account and billing information for the authenticated customer.

**Response:** A JSON **array** containing one or more customer objects. Always take index `[0]`.

**Example response:**
```json
[
  {
    "CustomerID": "100139032",
    "FirstName": "Jane",
    "LastName": "Smith",
    "EmailAddress": "jane.smith@example.com",
    "MobileNumber": "0400000000",
    "HasSolarProduct": true,
    "HasHadPAYGProduct": true,
    "HasPAYGProduct": false,
    "ProductLevel": "Standard",
    "Premises": [
      {
        "ServiceAgreementID": "100000001",
        "IsActive": false,
        "AccountStatus": "CLOST",
        "Address": "1 OLD ST SUBURB 7000 TAS",
        "EstimatedBalance": null,
        "AverageDailyUsage": 9.67,
        "Meters": []
      },
      {
        "ServiceAgreementID": "118004920",
        "IsActive": true,
        "AccountStatus": "ACTIVE",
        "Address": "1 NEW ST SUBURB 7000 TAS",
        "HasSolar": true,
        "EstimatedBalance": -114.12,
        "AmountOwed": 0.0,
        "UnbilledAmount": -106.79,
        "AverageDailyUsage": 9.05,
        "UsageDaysRemaining": 0,
        "BillTotalAmount": 0.0,
        "BillDue": null,
        "HasPAYGPlus": true,
        "CurrentTimeOfUse": "T93",
        "CurrentTimeOfUseType": "TIME_OF_USE",
        "LifeSupport": "N",
        "Meters": [
          {
            "MeterID": "8000000000",
            "NMI": "8000000000",
            "MeterType": "COMMS4D",
            "BadgeNumber": null,
            "NetworkTarriffs": null
          }
        ]
      }
    ]
  }
]
```

**Critical notes:**
- The `Premises` array may contain **multiple entries** including old, closed accounts (`AccountStatus: "CLOST"`, `IsActive: false`)
- Always select the **active premise** (`IsActive: true`) — closed premises may have a different (wrong) `ServiceAgreementID`
- Billing fields (`EstimatedBalance`, `AmountOwed`, `UnbilledAmount`, `AverageDailyUsage`, `BillTotalAmount`, etc.) are on the **premise object**, not the top-level customer object
- `EstimatedBalance` and `UsageDaysRemaining` may be `null` for standard billing accounts (non-PAYG)
- The `NMI` (National Metering Identifier) in `Meters[0]` is needed as a query parameter for the usage endpoint

**Additional premise fields (may be null depending on account state):**

| Field | Type | Description |
|-------|------|-------------|
| `BillDue` | date string or null | Date the current bill is due for payment |
| `BillOverDueAmount` | float or null | Amount overdue (0 when not overdue) |
| `NumberOfUnpaidBills` | int or null | Count of unpaid bills |
| `CurrentTimeOfUse` | string or null | Active tariff code (e.g. `"T93"`) |
| `CurrentTimeOfUsePeriodEndDate` | date string or null | When the current tariff contract period ends |
| `HasActivePaymentExtension` | bool | Whether a payment extension arrangement is active |
| `HasActivePaymentPlans` | bool | Whether a payment plan is active |

**Additional customer root fields:**

| Field | Type | Description |
|-------|------|-------------|
| `UnreadNotificationsCount` | int | Number of unread in-app notifications |
| `HasSolarProduct` | bool | Whether the account has a solar product |

---

### `GET /api/usage/{timespan}`

Returns metered usage records for the specified time period.

**Path parameter:**

| Value | Description |
|-------|-------------|
| `day` | One day of hourly records |
| `week` | Seven days of daily records |
| `month` | One month of daily records |
| `quarter` | One quarter of daily records |
| `year` | One year of monthly records |

**Query parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `serviceAgreementID` | Yes | From the **active** premise (`IsActive: true`) |
| `customerId` | Yes | From the top-level customer object (`CustomerID`) |
| `index` | Yes | `-1` = most recent period, `-2` = previous, down to `-9` |
| `nmi` | Recommended | NMI from `Meters[0].NMI` — required to get non-null usage values |

**Example request:**
```
GET /api/usage/day?serviceAgreementID=118004920&customerId=100139032&index=-1&nmi=8000000000
```

**Example response:**
```json
{
  "StartDate": "2026-04-05T14:00:00Z",
  "EndDate": "2026-04-06T14:00:00Z",
  "NoDataFlag": false,
  "NoDataDayThresholdExceededFlag": false,
  "ServiceAgreementID": "118004920",
  "HasSolarTariff": true,
  "TimeMeasureCount": 1,
  "SummaryTotals": {
    "DayContainsSubstitutedUsage": false,
    "HasDailyBillSegments": false,
    "KilowattHourUsage": {
      "T140": 5.117,
      "T93OFFPEAK": 15.206,
      "T93PEAK": 12.937,
      "Total": 33.26
    },
    "DollarValueUsage": {
      "T140": -0.449,
      "T93OFFPEAK": 2.537,
      "T93PEAK": 4.590,
      "Other": 1.512,
      "Total": 8.190
    },
    "TariffTypes": ["T140", "T93OFFPEAK", "T93PEAK"]
  },
  "ServiceAgreements": {
    "118004920": {
      "Id": "118004920",
      "StartDate": "2026-02-24T13:00:00+00:00",
      "EndDate": "0001-01-01T00:00:00"
    }
  },
  "MeteredUsageRecords": [
    {
      "StartTime": "2026-04-05T14:00:00Z",
      "EndTime": "2026-04-06T14:00:00Z",
      "TimeMeasureUnit": "Day",
      "TimeMeasureCount": 1,
      "HasSubstitutedData": false,
      "KilowattHourUsage": null,
      "KilowattHourUsageAEST": null,
      "DollarValueUsage": {
        "T140": -0.449,
        "T93OFFPEAK": 2.537,
        "T93PEAK": 4.590
      }
    },
    {
      "StartTime": "2026-04-05T14:00:00Z",
      "EndTime": "2026-04-05T15:00:00Z",
      "TimeMeasureUnit": "Hour",
      "TimeMeasureCount": 1,
      "HasSubstitutedData": false,
      "KilowattHourUsage": {
        "T140": 0.0,
        "T93OFFPEAK": 1.161
      },
      "KilowattHourUsageAEST": null,
      "DollarValueUsage": null
    },
    {
      "StartTime": "2026-04-05T15:00:00Z",
      "EndTime": "2026-04-05T16:00:00Z",
      "TimeMeasureUnit": "Hour",
      "TimeMeasureCount": 1,
      "HasSubstitutedData": false,
      "KilowattHourUsage": {
        "T140": 0.153,
        "T93PEAK": 1.639
      },
      "KilowattHourUsageAEST": null,
      "DollarValueUsage": null
    }
  ],
  "NonMeteredUsageRecords": [
    {
      "Description": "Supply Charge - Residential Time of Use - Tariff 93",
      "DollarAmount": 1.512
    }
  ]
}
```

---

### `GET /api/powerhour/upcoming-active`

Returns current and upcoming Power Hour events for the authenticated account.

**No query parameters required** — account is determined from the bearer token.

**Response:** A JSON array of Power Hour event objects. Empty array if no upcoming events.

**Example response:**
```json
[
  {
    "EventName": "April Flash Event",
    "PowerHourEventId": 92,
    "StartDateTime": "2026-04-09T08:55:47",
    "OfferExpiryDateTime": "2026-04-26T15:55:00",
    "TimeslotAccepted": {
      "PowerHourTimeSlotId": 750,
      "StartDateTime": "2026-04-24T16:00:00",
      "EndDateTime": "2026-04-24T19:00:00",
      "ExpiryDateTime": "2026-04-24T15:55:00"
    },
    "TimeslotAll": [
      {
        "PowerHourTimeSlotId": 741,
        "StartDateTime": "2026-04-23T10:00:00",
        "EndDateTime": "2026-04-23T13:00:00",
        "ExpiryDateTime": "2026-04-23T09:55:00"
      }
    ],
    "Customer": {
      "AccountId": "118004920",
      "Nmi": "8000000000",
      "Usage": null,
      "Cost": null,
      "CalculatedDateTime": null,
      "ExportedDateTime": null,
      "AcceptedDateTime": null,
      "SPID": null,
      "Tariff": null,
      "DataQuality": null,
      "IsFlagged": false
    }
  }
]
```

**Field reference:**

| Field | Type | Description |
|-------|------|-------------|
| `EventName` | string | Human-readable event name |
| `PowerHourEventId` | int | Unique event identifier |
| `StartDateTime` | local datetime | When the event was announced (naive, Australia/Hobart) |
| `OfferExpiryDateTime` | local datetime | Deadline to select a timeslot (naive, Australia/Hobart) |
| `TimeslotAccepted` | object or null | The timeslot the customer has accepted; `null` if no selection made yet |
| `TimeslotAccepted.StartDateTime` | local datetime | When the customer's free-power window begins |
| `TimeslotAccepted.EndDateTime` | local datetime | When the customer's free-power window ends |
| `TimeslotAll` | array | All available timeslots to choose from |
| `Customer.Usage` | float or null | kWh used during the event — populated after the event completes |
| `Customer.Cost` | float or null | Savings earned during the event — populated after the event completes |

**Key notes:**
- All `StartDateTime`, `EndDateTime`, and `OfferExpiryDateTime` values are **naive local time** (Australia/Hobart) with **no timezone suffix** — must be interpreted as `Australia/Hobart` when converting to UTC
- `TimeslotAccepted` is `null` when the customer has not yet selected a timeslot
- `TimeslotAccepted.StartDateTime` and `TimeslotAccepted.EndDateTime` define the exact free-power window — these map to the `Power Hour Start` and `Power Hour End` HA sensors
- `OfferExpiryDateTime` is typically 5 minutes before the last available timeslot starts
- `TimeslotAll` offers multiple days and time windows to choose from; each slot has its own `ExpiryDateTime` (5 min before that slot starts)
- The event-level `StartDateTime` is when the event was **announced**, not when free power starts — the timeslot `StartDateTime` is what matters for determining the free-power window

---

### `GET /api/powerhour/all`

Returns all Power Hour events including completed historical events. Structure is identical to `/upcoming-active`.

**No query parameters required.**

Used to calculate total lifetime Power Hour savings by summing `abs(Customer.Cost)` across all events where `Customer.Cost` is not null.

---

### `GET /api/usage/billing-period`

Returns metered usage totals for the entire current billing cycle (typically a quarter).

**Query parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `serviceAgreementID` | Yes | From the active premise |
| `customerId` | Yes | From the top-level customer object |

**Response structure:** Same shape as `/api/usage/day` — `SummaryTotals`, `MeteredUsageRecords` (day-level), `NonMeteredUsageRecords`. The day-level `MeteredUsageRecords` contain `DollarValueUsage` only; `KilowattHourUsage` is null on day records.

**Most useful fields:**

```json
{
  "SummaryTotals": {
    "KilowattHourUsage": { "T140": 42.3, "T93OFFPEAK": 310.1, "T93PEAK": 220.5, "Total": 530.6 },
    "DollarValueUsage": { "T140": -3.71, "T93OFFPEAK": 51.69, "T93PEAK": 78.25, "Other": 45.00, "Total": 171.23 }
  }
}
```

**Note:** `Total` in `KilowattHourUsage` excludes T140 (solar). `Total` in `DollarValueUsage` includes the supply charge (`Other`). T140 dollars are negative (credit).

---

### `GET /api/payment/activepayment/{accountNumber}`

Returns which payment methods are currently active for an account.

**Path parameter:** `{accountNumber}` = `ServiceAgreementID` from the active premise.

**No query parameters required.**

**Response:**

```json
{
  "IsDirectDebitActive": true,
  "IsAutoPaymentActive": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `IsDirectDebitActive` | bool | Whether a direct debit arrangement is active |
| `IsAutoPaymentActive` | bool | Whether auto-payment (card) is configured |

---

## Usage response — detailed field reference

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `StartDate` | ISO 8601 UTC | Start of the period |
| `EndDate` | ISO 8601 UTC | End of the period |
| `NoDataFlag` | bool | `true` even when records exist and `SummaryTotals` is zeroed — **do not use this to skip processing**. Records may still contain valid hourly kWh data. |
| `HasSolarTariff` | bool | Whether a solar feed-in tariff is active |
| `ServiceAgreementID` | string | The service agreement ID used for this query |
| `SummaryTotals` | object | Aggregated totals for the period (reliable when correct `serviceAgreementID` is used) |
| `MeteredUsageRecords` | array | One record per time period — see below |
| `NonMeteredUsageRecords` | array | Fixed charges (supply charge, etc.) |
| `ServiceAgreements` | object | Map of service agreement IDs with their date ranges |

### `SummaryTotals`

| Field | Type | Description |
|-------|------|-------------|
| `KilowattHourUsage` | object | kWh by tariff key + `Total` |
| `DollarValueUsage` | object | Dollars by tariff key + `Other` (supply charge) + `Total` |
| `TariffTypes` | array | List of active tariff keys for this account |
| `DayContainsSubstitutedUsage` | bool | Whether any interval used substituted (estimated) data |

### `MeteredUsageRecords` items

Each record covers one time period. For `timespan=day`, the array contains:
- **1 Day record** (`TimeMeasureUnit: "Day"`) — has `DollarValueUsage` populated, `KilowattHourUsage` null
- **24 Hour records** (`TimeMeasureUnit: "Hour"`) — has `KilowattHourUsage` populated, `DollarValueUsage` null

| Field | Type | Description |
|-------|------|-------------|
| `StartTime` | ISO 8601 UTC | Period start |
| `EndTime` | ISO 8601 UTC | Period end |
| `TimeMeasureUnit` | string | `"Hour"`, `"Day"`, `"Week"`, `"Month"` |
| `TimeMeasureCount` | int | Always `1` |
| `HasSubstitutedData` | bool | Whether this interval used estimated data |
| `KilowattHourUsage` | object or null | kWh by tariff key — present on Hour records |
| `KilowattHourUsageAEST` | object or null | Alternative kWh in AEST — observed always null |
| `DollarValueUsage` | object or null | Dollars by tariff key — present on Day record only |

---

## Tariff keys

Tariff keys appear as keys within `KilowattHourUsage` and `DollarValueUsage` objects.

| Key | Description |
|-----|-------------|
| `T93PEAK` | Time of Use — Peak rate consumption |
| `T93OFFPEAK` | Time of Use — Off-peak rate consumption |
| `T31` | Flat rate — General power |
| `T41` | Flat rate — Controlled load (heating) |
| `T140` | Solar feed-in / export — **negative dollar value = earnings** |
| `Other` | Supply (daily fixed) charge — appears in `DollarValueUsage` `SummaryTotals` only, **not a tariff** |
| `Total` | Sum of all consumption tariffs — appears in `SummaryTotals` only |

**Important:** `T140` kWh represents solar energy exported to the grid (always positive). The corresponding `DollarValueUsage.T140` is **negative** because it is a credit to the customer.

**Important:** `Other` in `DollarValueUsage` is the **supply charge** (daily fixed fee), not solar. It comes from `NonMeteredUsageRecords` and appears in the summary total but not in individual hour records.

---

## Dates and timezones

All `StartDate`, `EndDate`, `StartTime`, and `EndTime` values are in **UTC**. Tasmania observes:
- AEST (UTC+10) in winter
- AEDT (UTC+11) in summer (daylight saving)

A day period starting at `2026-04-05T14:00:00Z` corresponds to **midnight AEST on April 6** (UTC+10).

---

## Data availability

Aurora Energy typically makes the previous day's meter data available at approximately **8–9am AEST** each morning. Until then, the API returns records with `KilowattHourUsage: null` and `SummaryTotals` with zero values.

Querying with `index=-1` returns the most recent available period. `index=-9` is the oldest available (approximately 9 days back).

---

## Known quirks

| Quirk | Detail |
|-------|--------|
| Response is a list | `GET /customers/current` returns a JSON **array**, not an object. Take `[0]`. |
| Multiple premises | The `Premises` array may include old closed accounts. Always filter for `IsActive: true`. |
| Wrong `serviceAgreementID` = null data | Using the ID from a closed premise returns 25 records with all null usage values and no error. |
| `NoDataFlag: true` with records | `NoDataFlag` is often `true` even when 25 records are returned and hourly kWh data is present. Do not use this flag to skip processing — check for non-zero values in `KilowattHourUsage` directly instead. |
| Power Hours datetimes are naive local | All datetime fields in `/powerhour/*` responses have no timezone suffix and represent `Australia/Hobart` local time. Must be localised before converting to UTC. |
| Power Hours `Cost` sign | `Customer.Cost` after a completed event may be negative (credit) or positive (savings amount) depending on API version — use `abs()` to get the savings value. |
| `accessToken` includes prefix | The `accessToken` value in login/refresh responses is `"bearer <token>"` — strip the prefix before using as a Bearer token. |
| `Accept` header required | Omitting `Accept: application/json` causes usage records to return null usage values. |
| `User-Agent` header | The API expects `User-Agent: python/auroraplus` — other values may work but this is the tested value. |
| `KilowattHourUsageAEST` | This field exists on all records but has been observed as always `null`. Its purpose is unknown. |
| Dollar data split | `DollarValueUsage` is only populated on the Day-level record, not on individual Hour records. kWh data is only on Hour records. |

---

## Example: computing daily totals from records

Since `SummaryTotals` is the most reliable source for daily totals, use it directly:

```python
summary = usage_response.get("SummaryTotals", {})
kwh = summary.get("KilowattHourUsage", {})
dollars = summary.get("DollarValueUsage", {})

total_kwh = kwh.get("Total")             # All consumption combined
solar_kwh = kwh.get("T140")              # Solar exported to grid

total_dollars = dollars.get("Total")     # Everything including supply charge
solar_earnings = abs(dollars.get("T140", 0))  # Credit for solar export
supply_charge = dollars.get("Other", 0)  # Daily fixed supply charge
```

For hourly breakdowns, iterate `MeteredUsageRecords` and filter for `TimeMeasureUnit == "Hour"`:

```python
for record in usage_response.get("MeteredUsageRecords", []):
    if record.get("TimeMeasureUnit") != "Hour":
        continue
    kwh_by_tariff = record.get("KilowattHourUsage") or {}
    hour_start = record.get("StartTime")
    consumption_kwh = sum(
        v for k, v in kwh_by_tariff.items()
        if k != "T140" and v is not None
    )
    solar_export_kwh = kwh_by_tariff.get("T140", 0) or 0
```

---

## References

- [LeighCurran/AuroraPlusHA](https://github.com/LeighCurran/AuroraPlusHA) — original community HA integration
- [shtrom/AuroraPlusHA](https://github.com/shtrom/AuroraPlusHA) — fork with HA 2025.11 fixes and auth improvements
- [LeighCurran/auroraplus](https://github.com/LeighCurran/auroraplus) — standalone Python library for the Aurora+ API
