import requests
import os
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime
import urllib.parse
import sys
import json
from cloudflare_utils import upload_to_cloudflare
from account_manager import get_account_for_upload, get_account_for_submission, get_all_accounts
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers to mimic a browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1"
}

# Add this near the top with other constants
SAVE_MODE = 1  # 1 = AI only, 2 = Similarity only, 3 = Both

def download_file(url, local_filename=None):
    """Download a file from a URL and save it locally"""
    if not local_filename:
        local_filename = os.path.basename(urllib.parse.urlparse(url).path)
        if not local_filename:
            local_filename = "downloaded_file"
    
    logger.info(f"Downloading file from {url}...")
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(local_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"File downloaded successfully to {os.path.abspath(local_filename)}")
        return os.path.abspath(local_filename)
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return None

def upload_document(file_path):
    """Upload a document to ScopedLens and return the submission ID"""
    logger.info(f"Uploading document: {file_path}")
    
    # Get the next account to use for upload
    account = get_account_for_upload()
    cookies = account["cookies"]
    logger.info(f"Using account: {account['email']}")
    
    # First, get the CSRF token from the create page
    create_url = "https://scopedlens.com/self-service/submission/create"
    
    try:
        # Get the create page to extract the CSRF token
        create_response = requests.get(create_url, cookies=cookies, headers=HEADERS)
        create_response.raise_for_status()
        
        # Parse the HTML to extract the CSRF token
        soup = BeautifulSoup(create_response.text, 'html.parser')
        csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        
        if not csrf_input:
            logger.error("Could not find CSRF token on the page")
            return None
        
        csrf_token = csrf_input.get('value')
        
        # Prepare the file for upload
        file_name = os.path.basename(file_path)
        
        # Prepare the form data
        form_data = {
            "csrfmiddlewaretoken": csrf_token,
            "region": "uk",
            "title": file_name,
            "exclude_small_matches_method": "disabled",
            "exclude_small_matches_value_words": "0",
            "exclude_small_matches_value_percentage": "0"
        }
        
        files = {
            "upload_document": (file_name, open(file_path, 'rb'), 'application/octet-stream')
        }
        
        # Add the CSRF token to the headers
        upload_headers = HEADERS.copy()
        upload_headers["Referer"] = create_url
        
        # Make the POST request to upload the document
        upload_response = requests.post(
            create_url,
            cookies=cookies,
            headers=upload_headers,
            data=form_data,
            files=files
        )
        
        # Close the file
        files["upload_document"][1].close()
        
        # Check if the upload was successful
        if upload_response.status_code == 200 or upload_response.status_code == 302:
            # The upload was successful, now we need to get the submission ID
            # We'll check the submissions page to find the most recent submission
            time.sleep(2)  # Wait a bit for the server to process the upload
            
            submissions_url = "https://scopedlens.com/self-service/submissions/"
            submissions_response = requests.get(submissions_url, cookies=cookies, headers=HEADERS)
            
            if submissions_response.status_code == 200:
                # Parse the HTML to find the most recent submission
                submissions_soup = BeautifulSoup(submissions_response.text, 'html.parser')
                submission_link = submissions_soup.select_one('#submission-row td:first-child a')
                
                if submission_link:
                    href = submission_link.get('href')
                    # Extract the UUID from the href
                    submission_id = href.split('/')[-1]
                    
                    # Associate submission with account
                    from account_manager import associate_submission_with_account
                    associate_submission_with_account(submission_id, account["email"])
                    
                    logger.info(f"Document uploaded successfully! Submission ID: {submission_id}")
                    return submission_id
                else:
                    logger.error("Could not find submission ID in the response")
            else:
                logger.error(f"Failed to retrieve submissions list. Status code: {submissions_response.status_code}")
        else:
            logger.error(f"Upload failed. Status code: {upload_response.status_code}")
            logger.error(f"Response content: {upload_response.text[:500]}...")
        
        return None
    
    except Exception as e:
        logger.error(f"An error occurred during upload: {str(e)}")
        return None

def check_submission(submission_id):
    """Check the status of a submission and return the indices and report links"""
    logger.info(f"Checking submission: {submission_id}")
    
    # Get the account associated with this submission
    account = get_account_for_submission(submission_id)
    cookies = account["cookies"]
    logger.info(f"Using account: {account['email']}")
    
    submission_url = f"https://scopedlens.com/self-service/submission/{submission_id}"
    
    try:
        submission_response = requests.get(submission_url, cookies=cookies, headers=HEADERS)
        
        if submission_response.status_code == 200:
            soup = BeautifulSoup(submission_response.text, 'html.parser')
            
            # Check for "Page not found" error
            error_text = soup.find('h1')
            if error_text and error_text.text.strip() == "Page not found":
                return {"error": "Invalid submission_id"}
            
            # Check for error message in the table (XPath: /html/body/div/div/div/div/table/tbody/tr[6])
            error_rows = soup.select('table tbody tr')
            for row in error_rows:
                header_cell = row.find('th')
                if header_cell and "Error:" in header_cell.text.strip():
                    error_content_cell = row.find('td')
                    if error_content_cell:
                        error_message = error_content_cell.text.strip()
                        return {"error": f"Document Error: {error_message}"}
            
            # Initialize flags to track what data is available
            has_required_index = False
            has_required_report = False
            
            # Initialize results dictionary
            results = {
                "status": "loading",  # Default status
                "similarity_index": None if SAVE_MODE == 1 else "Not available",
                "ai_index": None if SAVE_MODE == 2 else "Not available",
                "similarity_report_url": None,
                "ai_report_url": None
            }
            
            # Create reports directory structure
            reports_dir = os.path.join('Reports', submission_id)
            os.makedirs(reports_dir, exist_ok=True)
            
            # Extract indices based on SAVE_MODE
            table_rows = soup.select('table tbody tr')
            for row in table_rows:
                if (SAVE_MODE in [2, 3]) and "Similarity Index:" in row.get_text():
                    td = row.find('td')
                    if td:
                        similarity_text = td.get_text(strip=True)
                        similarity_match = re.search(r'(\d+)\s*%', similarity_text)
                        if similarity_match:
                            results['similarity_index'] = similarity_match.group(1) + '%'
                            if SAVE_MODE == 2:
                                has_required_index = True
                
                if (SAVE_MODE in [1, 3]) and "AI Writing Index:" in row.get_text():
                    td = row.find('td')
                    if td:
                        ai_text = td.get_text(strip=True)
                        ai_match = re.search(r'(\d+)\s*%', ai_text)
                        if ai_match:
                            results['ai_index'] = ai_match.group(1) + '%'
                            if SAVE_MODE == 1:
                                has_required_index = True
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Process reports based on SAVE_MODE
            if SAVE_MODE in [2, 3]:
                similarity_link = soup.find('a', string=re.compile("Download Similarity Report"))
                if similarity_link:
                    local_path = os.path.join(reports_dir, f"similarity_report_{timestamp}.pdf")
                    response = requests.get(similarity_link['href'], cookies=cookies, headers=HEADERS)
                    if response.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(response.content)
                        cloudflare_url = upload_to_cloudflare(
                            local_path,
                            f'reports/{submission_id}/similarity_report_{timestamp}.pdf'
                        )
                        results['similarity_report_url'] = cloudflare_url
                        if SAVE_MODE == 2:
                            has_required_report = True
                        os.remove(local_path)
            
            if SAVE_MODE in [1, 3]:
                ai_link = soup.find('a', string=re.compile("Download AI Writing Report"))
                if ai_link:
                    local_path = os.path.join(reports_dir, f"ai_report_{timestamp}.pdf")
                    response = requests.get(ai_link['href'], cookies=cookies, headers=HEADERS)
                    if response.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(response.content)
                        cloudflare_url = upload_to_cloudflare(
                            local_path,
                            f'reports/{submission_id}/ai_report_{timestamp}.pdf'
                        )
                        results['ai_report_url'] = cloudflare_url
                        if SAVE_MODE == 1:
                            has_required_report = True
                        os.remove(local_path)
            
            # Update status based on what data is available
            if SAVE_MODE == 3:
                # For mode 3, need both AI and Similarity data
                if (results['ai_index'] not in [None, "Not available"] and 
                    results['similarity_index'] not in [None, "Not available"] and
                    results['ai_report_url'] and results['similarity_report_url']):
                    results['status'] = "done"
            else:
                # For modes 1 or 2, need the respective data
                if has_required_index and has_required_report:
                    results['status'] = "done"
            
            # Filter out None values before saving to JSON
            results = {k: v for k, v in results.items() if v is not None}
            
            # Save results to JSON
            with open(os.path.join(reports_dir, 'results.json'), 'w') as f:
                json.dump(results, f, indent=4)
            
            return results
            
        else:
            return {"error": f"HTTP Error: {submission_response.status_code}"}
    
    except Exception as e:
        return {"error": str(e)}

def download_reports(submission_id, results):
    """Download the reports for a submission"""
    # Get the account associated with this submission
    account = get_account_for_submission(submission_id)
    cookies = account["cookies"]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if results["similarity_url"]:
        try:
            similarity_report_response = requests.get(results["similarity_url"], cookies=cookies, headers=HEADERS)
            if similarity_report_response.status_code == 200:
                similarity_report_filename = f"similarity_report_{submission_id}_{timestamp}.pdf"
                with open(similarity_report_filename, "wb") as file:
                    file.write(similarity_report_response.content)
                logger.info(f"Similarity Report downloaded to: {os.path.abspath(similarity_report_filename)}")
            else:
                logger.error(f"Failed to download Similarity Report. Status code: {similarity_report_response.status_code}")
        except Exception as e:
            logger.error(f"Error downloading Similarity Report: {str(e)}")
    else:
        logger.error("Similarity Report URL not available")
    
    if results["ai_url"]:
        try:
            ai_report_response = requests.get(results["ai_url"], cookies=cookies, headers=HEADERS)
            if ai_report_response.status_code == 200:
                ai_report_filename = f"ai_writing_report_{submission_id}_{timestamp}.pdf"
                with open(ai_report_filename, "wb") as file:
                    file.write(ai_report_response.content)
                logger.info(f"AI Writing Report downloaded to: {os.path.abspath(ai_report_filename)}")
            else:
                logger.error(f"Failed to download AI Writing Report. Status code: {ai_report_response.status_code}")
        except Exception as e:
            logger.error(f"Error downloading AI Writing Report: {str(e)}")
    else:
        logger.error("AI Writing Report URL not available")

def check_quota():
    """Check the remaining quota from ScopedLens for all accounts"""
    logger.info("Checking quota for all accounts")
    create_url = "https://scopedlens.com/self-service/submission/create"
    all_accounts = get_all_accounts()
    
    quota_results = []
    total_used = 0
    total_limit = 0
    
    if not all_accounts:
        logger.error("No accounts available for quota check")
        return {"accounts": [], "total_used": 0, "total_limit": 0, "remaining": 0}
    
    for account in all_accounts:
        try:
            cookies = account["cookies"]
            logger.info(f"Checking quota for account: {account['email']}")
            response = requests.get(create_url, cookies=cookies, headers=HEADERS)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                quota_element = soup.select_one("div > div > div > h6")
                if quota_element:
                    # Get the text and replace all whitespace (including newlines) with single spaces
                    quota_text = re.sub(r'\s+', ' ', quota_element.text.strip())
                    logger.info(f"Raw quota text: {quota_text}")
                    
                    # Extract the numbers using regex
                    quota_match = re.search(r'(\d+)\s*/\s*(\d+)', quota_text)
                    if quota_match:
                        used = int(quota_match.group(1))
                        limit = int(quota_match.group(2))
                        total_used += used
                        total_limit += limit
                        # Format as a single string without extra spaces
                        quota = f"{used}/{limit}"
                        logger.info(f"Parsed quota: {used}/{limit}")
                    else:
                        # Simple cleanup as fallback
                        clean_text = quota_text.replace("Your Quota:", "").replace("Reset everyday", "").strip()
                        # Further replace any remaining newlines
                        quota = clean_text.replace("\n", "")
                        logger.warning(f"Could not parse quota numbers, using raw text: {quota}")
                else:
                    quota = "Quota information not found"
                    logger.warning("Quota element not found in page")
            else:
                quota = f"Error: Could not fetch quota (HTTP {response.status_code})"
                logger.error(f"Error fetching quota: HTTP {response.status_code}")
                
            quota_results.append({
                "email": account["email"],
                "quota": quota
            })
            
        except Exception as e:
            logger.error(f"Exception checking quota for {account['email']}: {str(e)}")
            quota_results.append({
                "email": account["email"],
                "quota": f"Error: {str(e)}"
            })
    
    remaining_submissions = total_limit - total_used
    logger.info(f"Total quota: {total_used}/{total_limit}, remaining: {remaining_submissions}")
    
    return {
        "accounts": quota_results,
        "total_used": total_used,
        "total_limit": total_limit,
        "remaining": remaining_submissions
    }

def main_menu():
    """Display the main menu and handle user choices"""
    while True:
        logger.info("\n" + "="*50)
        logger.info("ScopedLens Document Checker")
        logger.info("="*50)
        logger.info("1. Upload a new file")
        logger.info("2. Check a file")
        logger.info("3. Check Quota")
        logger.info("4. Quit")
        
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == "1":
            # Upload a new file
            file_url = input("\nEnter the URL of the file to upload: ")
            
            # Download the file
            local_file = download_file(file_url)
            
            if local_file:
                # Upload the file
                submission_id = upload_document(local_file)
                
                # Delete the downloaded file
                os.remove(local_file)
                logger.info(f"Deleted temporary file: {local_file}")
                
                if submission_id:
                    logger.info(f"\nYour submission ID is: {submission_id}")
                    logger.info("Please save this ID to check the status later.")
                    
                    # Ask if the user wants to check the status now
                    check_now = input("\nDo you want to check the status now? (y/n): ")
                    if check_now.lower() == 'y':
                        # Wait a bit for processing
                        logger.info("\nWaiting for processing to complete...")
                        time.sleep(10)
                        
                        # Check the submission
                        results = check_submission(submission_id)
                        
                        if results:
                            logger.info("\nResults:")
                            logger.info(f"Similarity Index: {results['similarity_index']}")
                            logger.info(f"AI Writing Index: {results['ai_index']}")
                            
                            if results["similarity_url"]:
                                logger.info(f"Similarity Report URL: {results['similarity_url']}")
                            else:
                                logger.info("Similarity Report not available yet")
                            
                            if results["ai_url"]:
                                logger.info(f"AI Writing Report URL: {results['ai_url']}")
                            else:
                                logger.info("AI Writing Report not available yet")
                            
                            # Ask if the user wants to download the reports
                            download_now = input("\nDo you want to download the reports? (y/n): ")
                            if download_now.lower() == 'y':
                                download_reports(submission_id, results)
            
        elif choice == "2":
            # Check a file
            submission_id = input("\nEnter the submission ID: ")
            results = check_submission(submission_id)
            
            if "error" in results:
                logger.error(f"\nError: {results['error']}")
            else:
                logger.info(f"\nStatus: {results['status']}")
                if results['status'] == "done":
                    if SAVE_MODE in [2, 3] and 'similarity_index' in results:
                        logger.info(f"Similarity Index: {results['similarity_index']}")
                    if SAVE_MODE in [1, 3] and 'ai_index' in results:
                        logger.info(f"AI Writing Index: {results['ai_index']}")
                    
                    if SAVE_MODE in [2, 3] and 'similarity_report_url' in results:
                        logger.info(f"\nSimilarity Report Download Link (expires in 3 days):")
                        logger.info(results['similarity_report_url'])
                    
                    if SAVE_MODE in [1, 3] and 'ai_report_url' in results:
                        logger.info(f"\nAI Writing Report Download Link (expires in 3 days):")
                        logger.info(results['ai_report_url'])
        
        elif choice == "3":
            # Check quota for all accounts
            logger.info("\nChecking quota for all accounts...")
            quota_data = check_quota()
            
            for result in quota_data["accounts"]:
                logger.info(f"Account {result['email']}: {result['quota']}")
            
            logger.info(f"\n{quota_data['remaining']} Submissions Left Today")
        
        elif choice == "4":
            # Quit
            logger.info("\nThank you for using ScopedLens Document Checker. Goodbye!")
            sys.exit(0)
        
        else:
            logger.error("\nInvalid choice. Please enter 1-4.")

if __name__ == "__main__":
    main_menu()