import os
import json
from datetime import datetime
import logging
from accounts import get_accounts, save_accounts

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Expire: April 12, 2025.
# Expire: April 20, 2025.

def init_accounts():
    """Initialize the accounts database - now just checks if it's accessible"""
    try:
        accounts_data = get_accounts()
        logger.info(f"Accounts initialized with {len(accounts_data.get('accounts', []))} accounts")
        return True
    except Exception as e:
        logger.error(f"Error initializing accounts database: {str(e)}")
        return False

def get_account_for_upload():
    """Get the next account to use for upload (rotation)"""
    try:
        accounts_data = get_accounts()
        
        current_index = accounts_data["current_account_index"]
        account = accounts_data["accounts"][current_index]
        
        # Rotate to next account
        next_index = (current_index + 1) % len(accounts_data["accounts"])
        accounts_data["current_account_index"] = next_index
        
        save_accounts(accounts_data)
        
        logger.info(f"Got account for upload: {account['email']}, next index: {next_index}")
        return account
    except Exception as e:
        logger.error(f"Error getting account for upload: {str(e)}")
        # Fallback to first account in case of error
        return get_account_by_index(0)

def get_account_by_index(index):
    """Get an account by its index"""
    try:
        accounts_data = get_accounts()
        
        if 0 <= index < len(accounts_data["accounts"]):
            return accounts_data["accounts"][index]
        else:
            logger.warning(f"Account index {index} out of range")
            return accounts_data["accounts"][0] if accounts_data["accounts"] else None
    except Exception as e:
        logger.error(f"Error getting account by index: {str(e)}")
        return None

def get_all_accounts():
    """Get all accounts"""
    try:
        accounts_data = get_accounts()
        return accounts_data["accounts"]
    except Exception as e:
        logger.error(f"Error getting all accounts: {str(e)}")
        return []

def associate_submission_with_account(submission_id, account_email):
    """Associate a submission ID with an account"""
    try:
        accounts_data = get_accounts()
        
        # Store submission association with timestamp
        accounts_data["submissions"][submission_id] = {
            "account_email": account_email,
            "timestamp": datetime.now().isoformat()
        }
        
        save_accounts(accounts_data)
        logger.info(f"Associated submission {submission_id} with account {account_email}")
        return True
    except Exception as e:
        logger.error(f"Error associating submission with account: {str(e)}")
        return False

def get_account_for_submission(submission_id):
    """Get the account associated with a submission ID"""
    try:
        accounts_data = get_accounts()
        
        # Look up the submission
        if submission_id in accounts_data["submissions"]:
            account_email = accounts_data["submissions"][submission_id]["account_email"]
            
            # Find account with this email
            for account in accounts_data["accounts"]:
                if account["email"] == account_email:
                    return account
            
            # If account with email wasn't found, try to parse email to get index
            logger.warning(f"Could not find account with email {account_email}, using fallback method")
            return get_account_by_index(0)
        else:
            # If submission not in database, use the first account
            logger.warning(f"Submission ID {submission_id} not found in database")
            return get_account_by_index(0)
    except Exception as e:
        logger.error(f"Error getting account for submission: {str(e)}")
        return get_account_by_index(0)

# Initialize accounts on module import
init_accounts()
