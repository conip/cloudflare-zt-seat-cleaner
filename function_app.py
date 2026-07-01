import logging
import azure.functions as func
import os
#from cloudflare_utils import main as cf_main

try:
    from cloudflare_utils import main as cf_main
    logging.info("✅ Successfully imported cloudflare_utils")
except Exception as e:
    logging.error("❌ Failed to import cloudflare_utils: %s", e)
    cf_main = None


app = func.FunctionApp()

#@app.timer_trigger(schedule="0 */5 * * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
@app.timer_trigger(schedule="0 0 1 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)

def cf_user_seats(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info('The timer is past due!')


    cf_api_token = os.environ['key_vault']
    logging.info('Using Key Vault: %s', cf_api_token[:5] + '...')
    logging.info('Starting Cloudflare seat check')
    try:
        # read toggles from app settings
        remove_older_than = int(os.getenv('REMOVE_OLDER_THAN_HOURS', '1'))
        dry_run = os.getenv('DRY_RUN', 'true').lower() in ('1', 'true', 'yes')
        if dry_run:
            logging.info('DRY_RUN is true, will just search for seats older than %d hours', remove_older_than)
        else:
            logging.info('DRY_RUN is false, will perform actual removals for seats older than %d hours', remove_older_than)
        
        result = cf_main(remove_older_than=remove_older_than, dry_run=dry_run)
        
        logging.info('Cloudflare seat check completed successfully')
        logging.info('Result: %s', str(result))
    except Exception as e:
        logging.exception('Error running Cloudflare seat check: %s', e)
