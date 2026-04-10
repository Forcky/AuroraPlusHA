"""Constants for the Aurora Energy integration."""
from datetime import timedelta

DOMAIN = "aurora_energy"

# Config entry keys
CONF_ID_TOKEN = "id_token"
CONF_SERVICE_AGREEMENT_ID = "service_agreement_id"
CONF_CUSTOMER_ID = "customer_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_REFRESH_COOKIE = "refresh_cookie"

# API
BASE_URL = "https://api.auroraenergy.com.au/api"
ENDPOINT_LOGIN = "/identity/LoginToken"
ENDPOINT_REFRESH = "/identity/refreshToken"
ENDPOINT_CUSTOMERS = "/customers/current"
ENDPOINT_USAGE = "/usage/{timespan}"
ENDPOINT_POWERHOUR_UPCOMING = "/powerhour/upcoming-active"
ENDPOINT_POWERHOUR_ALL      = "/powerhour/all"

POLL_INTERVAL = timedelta(hours=1)

# Tariff names as returned by the API
TARIFF_T41 = "T41"
TARIFF_T31 = "T31"
TARIFF_T140 = "T140"          # Solar feed-in / export (negative dollars = earnings)
TARIFF_OTHER = "Other"        # Supply charge (non-metered, not solar)
TARIFF_TOTAL = "Total"
TARIFF_T93PEAK    = "T93PEAK"    # Time-of-use peak
TARIFF_T93OFFPEAK = "T93OFFPEAK" # Time-of-use off-peak

# Timezone for Aurora Energy Tasmania
TZ_HOBART = "Australia/Hobart"

# Sensor data keys (used to look up values from coordinator.data)
SENSOR_ESTIMATED_BALANCE = "estimated_balance"
SENSOR_AMOUNT_OWED = "amount_owed"
SENSOR_UNBILLED_AMOUNT = "unbilled_amount"
SENSOR_AVG_DAILY_USAGE = "average_daily_usage"
SENSOR_DAYS_REMAINING = "usage_days_remaining"
SENSOR_BILL_TOTAL = "bill_total_amount"

SENSOR_TOTAL_KWH = "total_kwh"
SENSOR_TOTAL_DOLLARS = "total_dollars"
SENSOR_T41_KWH = "t41_kwh"
SENSOR_T41_DOLLARS = "t41_dollars"
SENSOR_T31_KWH = "t31_kwh"
SENSOR_T31_DOLLARS = "t31_dollars"
SENSOR_SOLAR_KWH = "solar_feedin_kwh"
SENSOR_SOLAR_DOLLARS = "solar_feedin_dollars"

SENSOR_T93PEAK_KWH        = "t93peak_kwh"
SENSOR_T93PEAK_DOLLARS    = "t93peak_dollars"
SENSOR_T93OFFPEAK_KWH     = "t93offpeak_kwh"
SENSOR_T93OFFPEAK_DOLLARS = "t93offpeak_dollars"

SENSOR_PH_STATUS             = "powerhour_status"
SENSOR_PH_EVENT_NAME         = "powerhour_event_name"
SENSOR_PH_START              = "powerhour_start"
SENSOR_PH_END                = "powerhour_end"
SENSOR_PH_SELECTION_DEADLINE = "powerhour_selection_deadline"
SENSOR_PH_TOTAL_SAVINGS      = "powerhour_total_savings"

# External statistic IDs for the Energy Dashboard
STAT_ID_TOTAL_KWH = f"{DOMAIN}:total_kwh"
STAT_ID_T41_KWH = f"{DOMAIN}:t41_kwh"
STAT_ID_T31_KWH = f"{DOMAIN}:t31_kwh"
STAT_ID_SOLAR_KWH = f"{DOMAIN}:solar_feedin_kwh"
STAT_ID_TOTAL_DOLLARS = f"{DOMAIN}:total_dollars"
STAT_ID_SOLAR_DOLLARS = f"{DOMAIN}:solar_feedin_dollars"
STAT_ID_T93PEAK_KWH    = f"{DOMAIN}:t93peak_kwh"
STAT_ID_T93OFFPEAK_KWH = f"{DOMAIN}:t93offpeak_kwh"

# Number of past days to backfill on first run (API supports up to index -9)
BACKFILL_DAYS = 9
