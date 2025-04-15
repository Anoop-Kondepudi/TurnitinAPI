import json
import os
import logging
from cloudflare_utils import init_cloudflare_client
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
R2_BUCKET_NAME = "files"  # Same bucket you're using for files
ACCOUNTS_KEY = "config/accounts.json"  # Path in bucket where accounts.json will be stored
ACCOUNTS_CACHE = None  # In-memory cache of accounts data
CACHE_TIMESTAMP = None  # When the cache was last updated

def get_accounts():
    """Get accounts data from Cloudflare R2 or cache"""
    global ACCOUNTS_CACHE, CACHE_TIMESTAMP
    
    # If cache is still fresh (less than 60 seconds old), use it
    if ACCOUNTS_CACHE and CACHE_TIMESTAMP and (datetime.now() - CACHE_TIMESTAMP).total_seconds() < 60:
        return ACCOUNTS_CACHE
    
    logger.info("Fetching accounts data from Cloudflare R2")
    client = init_cloudflare_client()
    
    try:
        # Check if accounts file exists in R2
        try:
            response = client.get_object(Bucket=R2_BUCKET_NAME, Key=ACCOUNTS_KEY)
            accounts_data = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Loaded accounts from R2, found {len(accounts_data.get('accounts', []))} accounts")
        except client.exceptions.NoSuchKey:
            # If not exists, initialize with default accounts from original code
            logger.info("Accounts file not found in R2, initializing default")
            accounts_data = create_default_accounts()
            save_accounts(accounts_data)
        
        # Update cache
        ACCOUNTS_CACHE = accounts_data
        CACHE_TIMESTAMP = datetime.now()
        
        return accounts_data
    except Exception as e:
        logger.error(f"Error getting accounts data: {str(e)}")
        
        # If we have a cached version, return that as fallback
        if ACCOUNTS_CACHE:
            logger.info("Using cached accounts data as fallback")
            return ACCOUNTS_CACHE
            
        # Otherwise create default
        logger.info("Creating default accounts as fallback")
        default_data = create_default_accounts()
        ACCOUNTS_CACHE = default_data
        CACHE_TIMESTAMP = datetime.now()
        return default_data

def save_accounts(accounts_data):
    """Save accounts data to Cloudflare R2"""
    global ACCOUNTS_CACHE, CACHE_TIMESTAMP
    
    logger.info(f"Saving accounts data to Cloudflare R2, current_account_index: {accounts_data.get('current_account_index')}")
    client = init_cloudflare_client()
    
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=ACCOUNTS_KEY,
            Body=json.dumps(accounts_data, indent=4),
            ContentType='application/json'
        )
        
        # Update cache
        ACCOUNTS_CACHE = accounts_data
        CACHE_TIMESTAMP = datetime.now()
        
        return True
    except Exception as e:
        logger.error(f"Error saving accounts data: {str(e)}")
        return False

def create_default_accounts():
    """Create default accounts data structure"""
    default_accounts = [
        {
            "email": "g8sl3btpyz@knmcadibav.com", #May 20, 2025
            "cookies": {
                "csrftoken": "7owBSKtM8jrZKJ4pbFIbfBrN9NXzv55G",
                "sessionid": "wmz3aad4j988ts3q8bu8y0nhtgm3sk0i"
            }
        },
        {
            "email": "zbj92r25s2@mkzaso.com", #May 20, 2025
            "cookies": {
                "csrftoken": "k2GGtCGGwSDuk3KzBUSc7XOrHRVA9plM",
                "sessionid": "y6vdgjeku2rt20ke3pr0ocnxvjpdzp80"
            }
        },
        {
            "email": "ed5ny72025@daouse.com", #May 20, 2025
            "cookies": {
                "csrftoken": "ABoIdFA5ZY6IPDvjWhbu8BXWc9J5liJn",
                "sessionid": "p9ve1fwghckhn2od55pzt8h11j438kaj"
            }
        },
        {
            "email": "ru4ubqxb3k@knmcadibav.com", #May 14, 2025
            "cookies": {
                "csrftoken": "sM6h40ehc1a40GNNdXFCsInz76N1vQEA",
                "sessionid": "7she6qjjol8nkmn70vpf5vsacyzsc4vz"
            }
        }
    ]
    
    return {
        "current_account_index": 0,
        "accounts": default_accounts,
        "submissions": {}
    }