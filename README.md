# Azure Function: Cloudflare User Seat Management

## Overview
This Azure Function automates the management of Cloudflare Zero Trust user seats. It periodically checks for inactive users and can optionally remove their access seats based on configurable parameters.

## Architecture
- **Main Function**: `cf_user_seats` (Timer Triggered Azure Function)
- **Utility Module**: `cloudflare_utils.py`
- **Runtime**: Python
- **Trigger**: Timer (Default: Once daily at 1 AM)

## Configuration

### Environment Variables
Required environment variables that must be set in the Azure Function App settings:

| Variable | Description | Required |
|----------|-------------|-----------|
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account identifier | Yes |
| `CLOUDFLARE_EMAIL` | Email associated with Cloudflare account | Yes |
| `CLOUDFLARE_TOKEN` | Cloudflare API token with appropriate permissions | Yes |
| `REMOVE_OLDER_THAN_HOURS` | Number of hours of inactivity before seat removal (default: 1) | No |
| `DRY_RUN` | If set to 'true', will only simulate removals (default: true) | No |
| `key_vault` | Reference to Azure Key Vault secret containing Cloudflare token | Yes |

## Components

### 1. Main Function (`function_app.py`)
```python
@app.timer_trigger(schedule="0 0 1 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
```
- Runs daily at 1 AM
- Handles configuration and orchestrates the seat management process
- Provides logging and error handling
- Configurable dry-run mode for testing

### 2. Cloudflare Utilities (`cloudflare_utils.py`)

#### Key Functions:

1. `check_env_vars()`
   - Validates presence of required environment variables
   - Returns None if any required variables are missing

2. `get_zero_trust_seats()`
   - Retrieves all Zero Trust users from Cloudflare
   - Uses Cloudflare's API endpoint: `/client/v4/accounts/{account_id}/access/users`
   - Returns complete user data including seat information

3. `extract_seat_uid_from_user(user)`
   - Extracts seat UID from user records
   - Handles different response formats from Cloudflare API
   - Returns seat identifier or None

4. `get_zero_trust_users_to_remove(all_users, remove_older_than_hours)`
   - Filters users based on inactivity period
   - Only targets users with access_seat=True and gateway_seat=False
   - Returns list of users eligible for removal

5. `remove_zero_trust_seats(users_to_remove, dry_run=True)`
   - Manages the actual seat removal process
   - Supports dry-run mode for testing
   - Uses PATCH request to `/accounts/{account_id}/access/seats`

6. `main(remove_older_than=1, dry_run=True)`
   - Orchestrates the entire process
   - Returns status and results dictionary

## Response Format

### Success Response
```json
{
    "status": "success",
    "total_users": <number>,
    "users_to_remove": <number>,
    "dry_run": <boolean>,
    "removal_result": <API_response_or_payload>
}
```

### Error Response
```json
{
    "status": "error",
    "error": "<error_message>"
}
```

## Best Practices and Security

1. **Dry Run Mode**
   - Always test with `DRY_RUN=true` first
   - Verify the users that would be removed before actual removal

2. **Error Handling**
   - Comprehensive error handling at each step
   - Detailed logging for troubleshooting

3. **Security**
   - Uses bearer token authentication
   - Supports Azure Key Vault integration
   - Minimal permission scope requirements

4. **Logging**
   - Extensive logging throughout the process
   - Includes user counts, removal candidates, and API responses

## Limitations and Considerations

1. Only removes users who:
   - Have access_seat=True and gateway_seat=False
   - Haven't logged in within the specified time period
   - Have valid seat identifiers

2. API rate limits and timeout considerations apply

## Monitoring

The function provides detailed logging that can be monitored through:
- Azure Function App logs
- Application Insights (if configured)
- Custom logging through Azure Monitor

## Troubleshooting

Common issues and solutions:
1. Missing environment variables: Check Azure Function App settings
2. API authentication failures: Verify Cloudflare token permissions
3. No users found: Verify account ID and API response
4. Failed removals: Check API response for specific error messages
