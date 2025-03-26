import os
import json
from datetime import datetime
import logging
import random
from accounts import get_accounts, save_accounts

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Expire: April 12, 2025.
# Expire: April 20, 2025.

def init_accounts():
    """Initialize the accounts"""
    accounts_data = get_accounts()
    logger.info(f"Accounts initialized with {len(accounts_data['accounts'])} accounts")
    return accounts_data

def get_account_for_upload():
    """Get the next account to use for uploading"""
    accounts_data = get_accounts()
    accounts = accounts_data["accounts"]
    current_index = accounts_data.get("current_account_index", 0)
    
    if not accounts:
        logger.error("No accounts available")
        return None
    
    # Use the current account
    account = accounts[current_index]
    
    # Update the index for next time
    next_index = (current_index + 1) % len(accounts)
    accounts_data["current_account_index"] = next_index
    save_accounts(accounts_data)
    
    return account

def get_account_for_submission(submission_id):
    """Get an account to use for checking a submission"""
    accounts_data = get_accounts()
    accounts = accounts_data["accounts"]
    submissions = accounts_data.get("submissions", {})
    
    # If there are no accounts, return None
    if not accounts:
        logger.error("No accounts available")
        return None
    
    # If this submission is associated with an account, use that account
    if submission_id in submissions:
        account_email = submissions[submission_id]["account_email"]
        for account in accounts:
            if account["email"] == account_email:
                return account
    
    # Otherwise, use a random account
    return random.choice(accounts)

def get_account_by_email(email):
    """Get an account by email"""
    accounts_data = get_accounts()
    for account in accounts_data["accounts"]:
        if account["email"] == email:
            return account
    return None

def get_all_accounts():
    """Get all accounts"""
    accounts_data = get_accounts()
    return accounts_data["accounts"]

def associate_submission_with_account(submission_id, account_email):
    """Associate a submission with an account"""
    accounts_data = get_accounts()
    if "submissions" not in accounts_data:
        accounts_data["submissions"] = {}
    
    accounts_data["submissions"][submission_id] = {
        "account_email": account_email,
        "timestamp": datetime.now().isoformat()
    }
    
    save_accounts(accounts_data)
    logger.info(f"Submission {submission_id} associated with account {account_email}")

def get_submission_to_account_map():
    """Get the mapping of submissions to accounts"""
    accounts_data = get_accounts()
    return accounts_data.get("submissions", {})

# Initialize accounts on module load
init_accounts()
