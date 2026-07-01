from datetime import datetime, timedelta, timezone
import os
import requests
import sys
import json
import logging
#-----------------------------------------------------

def check_env_vars():
    """Check if all required environment variables are set"""
    required_vars = ['CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_EMAIL', 'CLOUDFLARE_TOKEN']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logging.info(f"Error: Missing environment variables: {', '.join(missing_vars)}")
        logging.info("\nPlease set them in keyvault + read it in env var of function app")
        for var in missing_vars:
            logging.info(f"Missing: {var}")
        return None
#-----------------------------------------------------
def get_zero_trust_seats():

    # This Function lists all Zero Trust users in the Cloudflare account (even expired ones).
    try:
        check_env_vars()
    except:
        logging.info("❌ Environment variables not properly set")
        return None
    
    # Retrieve Cloudflare account details from environment variables
    account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    cloudflare_email = os.getenv('CLOUDFLARE_EMAIL')
    cloudflare_token = os.getenv('CLOUDFLARE_TOKEN')
    
    logging.info(f"Using Account ID: {account_id}")
    logging.info(f"Using Email: {cloudflare_email}")
    logging.info(f"Token starts with: {cloudflare_token[:10]}...")
    
    # Approach 1: Try Zero Trust organizations endpoint
    logging.info("\n🔍  Trying Zero Trust organizations endpoint...")
    orgs_url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/access/users'
    headers = {
        'Authorization': f'Bearer {cloudflare_token}',
        'X-Auth-Email': f'{cloudflare_email}',
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.get(orgs_url, headers=headers)
        #print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                result = data.get('result', {})
                #logging.info("Response:")
                #print(json.dumps(result, indent=2))
                return data
            else:
                logging.info("❌ Organizations endpoint returned success=false")
                logging.info("Errors:", data.get('errors', []))
                return None
        else:
            logging.info(f"❌ endpoint failed: {response.text}")
            return None
    except Exception as e:
        logging.info(f"❌ Error with endpoint: {e}")
        return None
    
#-----------------------------------------------------
def extract_seat_uid_from_user(user):
    """
    Try to find a seat UID inside a user record.
    Cloudflare may present seat identifiers in different keys depending on endpoint/results.
    This function attempts to find a sensible identifier for the seat.
    """
    # common direct key
    if user.get('seat_uid'):
        return user['seat_uid']

    # sometimes 'id' is the seat id (fallback)
    if user.get('id'):
        return user['id']

    # some responses can include seats list (take first)
    seats = user.get('seats') or user.get('seat') or []
    if isinstance(seats, list) and len(seats) > 0:
        first = seats[0]
        if isinstance(first, dict):
            for key in ('seat_uid', 'id', 'seat_id'):
                if first.get(key):
                    return first.get(key)

    return None
#-----------------------------------------------------
def get_zero_trust_users_to_remove(all_users, remove_older_than_hours):
    """
    Filter all_users to those that have not logged in within remove_older_than_hours.
    Returns list of user dicts that should be removed (with seat_uid extracted where possible).
    """
    if all_users is None:
        logging.info("No users provided")
        return []

    # Accept either full API response object or list
    users_list = all_users
    if isinstance(all_users, dict) and 'result' in all_users:
        users_list = all_users['result']

    time_threshold = timedelta(hours=remove_older_than_hours)
    current_time = datetime.now(timezone.utc)

    filtered_users = []
    for user in users_list:
        # Some users might not have last_successful_login — treat them as older
        last_successful = user.get('last_successful_login')
        name = user.get('name')
        access_seat = user.get('access_seat')
        gateway_seat = user.get('gateway_seat')

        if access_seat is True and gateway_seat is False:                   # remove only these users who dont use WARP (gateway_seat=false)
            if not last_successful:
                needs_removal = True
            else:
                try:
                    last_login_time = datetime.fromisoformat(last_successful.replace('Z', '+00:00'))
                    needs_removal = (current_time - last_login_time) > time_threshold
                except Exception:
                    # If parsing fails, be conservative and mark for removal
                    needs_removal = True

            if needs_removal:
                seat_uid = extract_seat_uid_from_user(user)
                filtered_users.append({
                    'seat_uid': seat_uid,
                    'id': user.get('id'),
                    'name': user.get('name'),
                    'email': user.get('email'),
                    'raw': user
                })

    logging.info(f"Number of users not logged in for {remove_older_than_hours} hours: {len(filtered_users)}")
    for u in filtered_users:
        logging.info(f"ID: {u['id']}, Name: {u['name']}, Email: {u['email']}, seat_uid: {u['seat_uid']}")
    return filtered_users

#-----------------------------------------------------
def remove_zero_trust_seats(users_to_remove, dry_run=True):
    """
    Build and send the PATCH request to /accounts/{account_id}/access/seats to disable seats.
    users_to_remove: list of dicts as returned by get_zero_trust_users_to_remove (must contain 'seat_uid' or 'id')
    dry_run: if True only prints the payload and won't call the API
    """

    if not users_to_remove:
        logging.info("No users to remove.")
        return None

    account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    cloudflare_email = os.getenv('CLOUDFLARE_EMAIL')
    cloudflare_token = os.getenv('CLOUDFLARE_TOKEN')
    #cloudflare_api_key = os.getenv('CLOUDFLARE_API_KEY')

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/access/seats"

    payload = []
    for u in users_to_remove:
        seat_uid = u.get('seat_uid') or u.get('id')
        if not seat_uid:
            logging.info(f"Skipping user without seat identifier: {u.get('email') or u.get('name')}")
            continue
        payload.append({
            "access_seat": False,
            "gateway_seat": False,
            "seat_uid": seat_uid
        })

    if not payload:
        logging.info("No valid seat UIDs found to remove.")
        return None

    logging.info("Payload to send:")
    logging.info(json.dumps(payload, indent=2))

    if dry_run:
        logging.info("dry_run=True -> not sending API request. Set dry_run=False to perform removal.")
        return payload

    headers = {
        'Content-Type': 'application/json'
    }
    # choose auth method
    if cloudflare_token:
        headers['Authorization'] = f'Bearer {cloudflare_token}'
    # else:
    #     # legacy API key method
    #     headers['X-Auth-Email'] = cloudflare_email
    #     headers['X-Auth-Key'] = cloudflare_api_key

    try:
        resp = requests.patch(url, headers=headers, json=payload)
        logging.info(f"PATCH status: {resp.status_code}")
        try:
            resp_json = resp.json()
            logging.info(json.dumps(resp_json, indent=2))
        except ValueError:
            logging.info("Response (non-json):", resp.text)
        if resp.status_code in (200, 201):
            logging.info("Seats updated successfully.")
        else:
            logging.info("Failed to update seats.")
        return resp
    except Exception as e:
        logging.error(f"Error calling seats PATCH: {e}")
        return None

# #-----------------------------------------------------

def main(remove_older_than=1, dry_run=True):
    """
    Main function to be called by Azure Function.
    Returns a dict with status and results.
    """
    try:
        logging.info("🔍 Cloudflare Zero Trust Information")
        
        all_users = get_zero_trust_seats()
        
        if not all_users or 'result' not in all_users:
            logging.error("Could not fetch users or empty result.")
            return {
                "status": "error",
                "error": "Could not fetch users or empty result"
            }
        
        # Log total users and find candidates for removal
        total_users = len(all_users['result'])
        logging.info("Number of total users: %d", total_users)
        
        users_to_remove = get_zero_trust_users_to_remove(all_users, remove_older_than)
        logging.info("Found %d users to potentially remove (older than %d hours)", 
                    len(users_to_remove), remove_older_than)
        
        # Remove seats based on dry_run flag
        removal_result = remove_zero_trust_seats(users_to_remove, dry_run=dry_run)
        
        return {
            "status": "success",
            "total_users": total_users,
            "users_to_remove": len(users_to_remove),
            "dry_run": dry_run,
            "removal_result": removal_result
        }
        
    except Exception as e:
        logging.exception("Error in cloudflare_utils.main: %s", e)
        return {
            "status": "error",
            "error": str(e)
        }




# # #=========================================================
# # # Keep this for standalone testing
# # if __name__ == "__main__":
# #     print("🔍 Cloudflare Zero Trust Information\n")

# #     all_users = get_zero_trust_seats()
# #     remove_older_than = 1  # hours

# #     print("\n" + "=" * 50)
# #     if not all_users or 'result' not in all_users:
# #         print("Could not fetch users or empty result.")
# #         sys.exit(1)

# #     # Print total users and find candidates for removal
# #     print(f"number of total users: {len(all_users['result'])}")
# #     users_to_remove = get_zero_trust_users_to_remove(all_users, remove_older_than)

# #     # Dry run first — change to dry_run=False to actually remove seats
# #     remove_zero_trust_seats(users_to_remove, dry_run=True)