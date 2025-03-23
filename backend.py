import httpx  # Replace requests with httpx
import os
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime
import urllib.parse
import sys
import json
from cloudflare_utils import upload_to_cloudflare, init_cloudflare_client, R2_BUCKET_NAME
from account_manager import get_account_for_upload, get_account_for_submission, get_all_accounts

# Proxy settings
PROXY_HOST = "144.229.117.13"
PROXY_PORT = "1337"
PROXY_USERNAME = "lho7SIZFaRh9"
PROXY_PASSWORD = "1inYc0RRMvYs"

# Configure proxy URL - URL encode credentials to handle special characters
PROXY_URL = f"http://{urllib.parse.quote(PROXY_USERNAME)}:{urllib.parse.quote(PROXY_PASSWORD)}@{PROXY_HOST}:{PROXY_PORT}"

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
    
    print(f"Downloading file from {url}...")
    
    try:
        transport = httpx.HTTPTransport(proxy=PROXY_URL)
        with httpx.Client(transport=transport) as client:
            response = client.get(url)
            response.raise_for_status()
            
            with open(local_filename, 'wb') as f:
                f.write(response.content)
        
        print(f"File downloaded successfully to {os.path.abspath(local_filename)}")
        return os.path.abspath(local_filename)
    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        return None

def upload_document(file_path):
    """Upload a document to ScopedLens and return the submission ID"""
    print(f"Uploading document: {file_path}")
    
    # Get the next account to use for upload
    account = get_account_for_upload()
    cookies = account["cookies"]
    print(f"Using account: {account['email']}")
    
    # First, get the CSRF token from the create page
    create_url = "https://scopedlens.com/self-service/submission/create"
    
    try:
        # Get the create page to extract the CSRF token
        transport = httpx.HTTPTransport(proxy=PROXY_URL)
        with httpx.Client(cookies=cookies, headers=HEADERS, transport=transport) as client:
            create_response = client.get(create_url)
            create_response.raise_for_status()
            
            # Parse the HTML to extract the CSRF token
            soup = BeautifulSoup(create_response.text, 'html.parser')
            csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
            
            if not csrf_input:
                print("Could not find CSRF token on the page")
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
            
            # Add the CSRF token to the headers
            upload_headers = HEADERS.copy()
            upload_headers["Referer"] = create_url
            
            # Make the POST request to upload the document
            with open(file_path, 'rb') as f:
                files = {"upload_document": (file_name, f, 'application/octet-stream')}
                upload_response = client.post(
                    create_url,
                    headers=upload_headers,
                    data=form_data,
                    files=files
                )
            
            # Check if the upload was successful
            if upload_response.status_code == 200 or upload_response.status_code == 302:
                # The upload was successful, now we need to get the submission ID
                # We'll check the submissions page to find the most recent submission
                time.sleep(2)  # Wait a bit for the server to process the upload
                
                submissions_url = "https://scopedlens.com/self-service/submissions/"
                submissions_response = client.get(submissions_url)
                
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
                        
                        print(f"Document uploaded successfully! Submission ID: {submission_id}")
                        return submission_id
                    else:
                        print("Could not find submission ID in the response")
                else:
                    print(f"Failed to retrieve submissions list. Status code: {submissions_response.status_code}")
            else:
                print(f"Upload failed. Status code: {upload_response.status_code}")
                print(f"Response content: {upload_response.text[:500]}...")
            
            return None
    
    except Exception as e:
        print(f"An error occurred during upload: {str(e)}")
        return None

def check_submission(submission_id):
    """Check the status of a submission and return the indices and report links"""
    print(f"Checking submission: {submission_id}")
    
    # Get the account associated with this submission
    account = get_account_for_submission(submission_id)
    cookies = account["cookies"]
    print(f"Using account: {account['email']}")
    
    submission_url = f"https://scopedlens.com/self-service/submission/{submission_id}"
    
    try:
        transport = httpx.HTTPTransport(proxy=PROXY_URL)
        with httpx.Client(cookies=cookies, headers=HEADERS, transport=transport) as client:
            submission_response = client.get(submission_url)
            
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
                        response = client.get(similarity_link['href'])
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
                        response = client.get(ai_link['href'])
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
                with open(os.path.join(reports_dir, 'results.json'), 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=4, ensure_ascii=False)
                
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
    
    transport = httpx.HTTPTransport(proxy=PROXY_URL)
    with httpx.Client(cookies=cookies, headers=HEADERS, transport=transport) as client:
        if "similarity_url" in results and results["similarity_url"]:
            try:
                similarity_report_response = client.get(results["similarity_url"])
                if similarity_report_response.status_code == 200:
                    similarity_report_filename = f"similarity_report_{submission_id}_{timestamp}.pdf"
                    with open(similarity_report_filename, "wb") as file:
                        file.write(similarity_report_response.content)
                    print(f"Similarity Report downloaded to: {os.path.abspath(similarity_report_filename)}")
                else:
                    print(f"Failed to download Similarity Report. Status code: {similarity_report_response.status_code}")
            except Exception as e:
                print(f"Error downloading Similarity Report: {str(e)}")
        else:
            print("Similarity Report URL not available")
        
        if "ai_url" in results and results["ai_url"]:
            try:
                ai_report_response = client.get(results["ai_url"])
                if ai_report_response.status_code == 200:
                    ai_report_filename = f"ai_writing_report_{submission_id}_{timestamp}.pdf"
                    with open(ai_report_filename, "wb") as file:
                        file.write(ai_report_response.content)
                    print(f"AI Writing Report downloaded to: {os.path.abspath(ai_report_filename)}")
                else:
                    print(f"Failed to download AI Writing Report. Status code: {ai_report_response.status_code}")
            except Exception as e:
                print(f"Error downloading AI Writing Report: {str(e)}")
        else:
            print("AI Writing Report URL not available")

def check_quota():
    """Check the remaining quota from ScopedLens for all accounts"""
    create_url = "https://scopedlens.com/self-service/submission/create"
    all_accounts = get_all_accounts()
    
    quota_results = []
    total_used = 0
    total_limit = 0
    debug_urls = []
    
    print(f"DEBUG: Starting quota check for {len(all_accounts)} accounts")
    
    for account in all_accounts:
        print(f"\nDEBUG: Checking quota for account: {account['email']}")
        try:
            cookies = account["cookies"]
            
            # Create a client with explicit encoding settings
            transport = httpx.HTTPTransport(proxy=PROXY_URL)
            
            # Add specific headers to help with encoding
            headers = HEADERS.copy()
            headers["Accept-Charset"] = "utf-8"
            
            print(f"DEBUG: Making request to {create_url} with proxy {PROXY_URL}")
            with httpx.Client(cookies=cookies, headers=headers, transport=transport) as client:
                # Make the request with explicit encoding handling
                response = client.get(create_url)
                
                print(f"DEBUG: Response status code: {response.status_code}")
                print(f"DEBUG: Response headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    # Save raw HTML for debugging
                    raw_html = response.content
                    debug_url = save_debug_html(raw_html.decode('utf-8', errors='replace'), account["email"])
                    if debug_url:
                        debug_urls.append({"email": account["email"], "debug_url": debug_url})
                        print(f"DEBUG: Saved HTML for {account['email']} at {debug_url}")
                    
                    # Try different encodings to find one that works
                    encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'windows-1252']
                    html_content = None
                    successful_encoding = None
                    
                    for encoding in encodings_to_try:
                        try:
                            print(f"DEBUG: Trying encoding: {encoding}")
                            # Force the encoding
                            response.encoding = encoding
                            html_content = response.text
                            
                            # Check if we can find the quota text with this encoding
                            soup = BeautifulSoup(html_content, 'html.parser')
                            quota_element = soup.select_one("div > div > div > h6")
                            
                            if quota_element:
                                print(f"DEBUG: Found h6 element with text: '{quota_element.text}'")
                                if "Your Quota:" in quota_element.text:
                                    print(f"DEBUG: Successfully decoded with {encoding}")
                                    successful_encoding = encoding
                                    break
                        except Exception as e:
                            print(f"DEBUG: Error with encoding {encoding}: {str(e)}")
                    
                    if not html_content:
                        print("DEBUG: All encodings failed, using 'replace' error handler")
                        # If all encodings failed, use the raw content and decode manually
                        html_content = response.content.decode('utf-8', errors='replace')
                    
                    print(f"DEBUG: Final encoding used: {successful_encoding or 'fallback with replace'}")
                    
                    # Try to extract quota directly from the HTML using regex
                    print("DEBUG: Attempting regex extraction directly from HTML")
                    quota_match = re.search(r'Your\s+Quota:\s*(\d+)\s*/\s*(\d+)', html_content)
                    
                    if quota_match:
                        used = int(quota_match.group(1))
                        limit = int(quota_match.group(2))
                        total_used += used
                        total_limit += limit
                        quota = f"{used}/{limit}"
                        print(f"DEBUG: Found quota via regex: {quota}")
                    else:
                        print("DEBUG: Regex extraction failed, trying BeautifulSoup")
                        # Try parsing with BeautifulSoup
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        # Try multiple selectors to find quota information
                        quota_element = None
                        selectors = [
                            "div > div > div > h6",
                            "h6",
                            ".quota-display",  # Add any class that might contain quota info
                            "div.container h6"
                        ]
                        
                        for selector in selectors:
                            print(f"DEBUG: Trying selector: {selector}")
                            elements = soup.select(selector)
                            print(f"DEBUG: Found {len(elements)} elements with selector {selector}")
                            
                            for element in elements:
                                print(f"DEBUG: Element text: '{element.text}'")
                                if "Quota" in element.text:
                                    quota_element = element
                                    print(f"DEBUG: Found quota element with text: '{element.text}'")
                                    break
                            if quota_element:
                                break
                        
                        if quota_element:
                            # Get the text and replace all whitespace with single spaces
                            quota_text = re.sub(r'\s+', ' ', quota_element.text.strip())
                            print(f"DEBUG: Cleaned quota text: '{quota_text}'")
                            
                            # Extract the numbers using regex
                            quota_match = re.search(r'(\d+)\s*/\s*(\d+)', quota_text)
                            if quota_match:
                                used = int(quota_match.group(1))
                                limit = int(quota_match.group(2))
                                total_used += used
                                total_limit += limit
                                quota = f"{used}/{limit}"
                                print(f"DEBUG: Extracted quota: {quota}")
                            else:
                                print("DEBUG: Failed to extract numbers with regex, trying direct number extraction")
                                # Try to extract any numbers from the text
                                numbers = re.findall(r'\d+', quota_text)
                                print(f"DEBUG: Found numbers: {numbers}")
                                
                                if len(numbers) >= 2:
                                    used = int(numbers[0])
                                    limit = int(numbers[1])
                                    total_used += used
                                    total_limit += limit
                                    quota = f"{used}/{limit}"
                                    print(f"DEBUG: Using first two numbers as quota: {quota}")
                                else:
                                    quota = "Could not parse quota numbers"
                                    print(f"DEBUG: Not enough numbers found in text")
                        else:
                            print("DEBUG: No quota element found with selectors, trying last resort search")
                            # Last resort: try to find any text containing quota information
                            found_quota = False
                            for tag in soup.find_all(['div', 'span', 'p', 'h6']):
                                if 'Quota' in tag.text:
                                    print(f"DEBUG: Found element with 'Quota' in text: '{tag.text}'")
                                    numbers = re.findall(r'\d+', tag.text)
                                    print(f"DEBUG: Numbers in this element: {numbers}")
                                    
                                    if len(numbers) >= 2:
                                        used = int(numbers[0])
                                        limit = int(numbers[1])
                                        total_used += used
                                        total_limit += limit
                                        quota = f"{used}/{limit}"
                                        found_quota = True
                                        print(f"DEBUG: Extracted quota: {quota}")
                                        break
                            
                            if not found_quota:
                                quota = "Quota information not found"
                                print("DEBUG: Could not find quota information in any element")
                else:
                    quota = f"Error: Could not fetch quota (HTTP {response.status_code})"
                    print(f"DEBUG: HTTP error {response.status_code}")
                
                quota_results.append({
                    "email": account["email"],
                    "quota": quota
                })
                
        except Exception as e:
            print(f"DEBUG: Exception in check_quota for {account['email']}: {str(e)}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            
            quota_results.append({
                "email": account["email"],
                "quota": f"Error: {str(e)}"
            })
    
    # Calculate remaining submissions
    remaining_submissions = max(0, total_limit - total_used)  # Ensure it's not negative
    print(f"\nDEBUG: Final calculation: {total_used}/{total_limit} = {remaining_submissions} remaining")
    
    result = {
        "accounts": quota_results,
        "total_used": total_used,
        "total_limit": total_limit,
        "remaining": remaining_submissions,
        "debug_urls": debug_urls
    }
    
    # Save debug information to a file
    debug_file = f"quota_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(debug_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"DEBUG: Saved debug information to {debug_file}")
    
    return result

def save_debug_html(html_content, account_email):
    """Save HTML content to Cloudflare R2 for debugging"""
    timestamp = int(time.time())
    object_name = f"debug/html_{account_email}_{timestamp}.html"
    
    client = init_cloudflare_client()
    
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=object_name,
            Body=html_content.encode('utf-8'),  # Ensure proper encoding
            ContentType='text/html; charset=utf-8'
        )
        
        # Generate a 24-hour accessible URL
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': R2_BUCKET_NAME,
                'Key': object_name
            },
            ExpiresIn=24*60*60  # 24 hours
        )
        
        return url
    except Exception as e:
        print(f"Error saving debug HTML: {str(e)}")
        return None

def main_menu():
    """Display the main menu and handle user choices"""
    while True:
        print("\n" + "="*50)
        print("ScopedLens Document Checker")
        print("="*50)
        print("1. Upload a new file")
        print("2. Check a file")
        print("3. Check Quota")
        print("4. Quit")
        
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
                print(f"Deleted temporary file: {local_file}")
                
                if submission_id:
                    print(f"\nYour submission ID is: {submission_id}")
                    print("Please save this ID to check the status later.")
                    
                    # Ask if the user wants to check the status now
                    check_now = input("\nDo you want to check the status now? (y/n): ")
                    if check_now.lower() == 'y':
                        # Wait a bit for processing
                        print("\nWaiting for processing to complete...")
                        time.sleep(10)
                        
                        # Check the submission
                        results = check_submission(submission_id)
                        
                        if results:
                            print("\nResults:")
                            if "similarity_index" in results:
                                print(f"Similarity Index: {results['similarity_index']}")
                            if "ai_index" in results:
                                print(f"AI Writing Index: {results['ai_index']}")
                            
                            if "similarity_url" in results and results["similarity_url"]:
                                print(f"Similarity Report URL: {results['similarity_url']}")
                            else:
                                print("Similarity Report not available yet")
                            
                            if "ai_url" in results and results["ai_url"]:
                                print(f"AI Writing Report URL: {results['ai_url']}")
                            else:
                                print("AI Writing Report not available yet")
                            
                            # Ask if the user wants to download the reports
                            download_now = input("\nDo you want to download the reports? (y/n): ")
                            if download_now.lower() == 'y':
                                download_reports(submission_id, results)
            
        elif choice == "2":
            # Check a file
            submission_id = input("\nEnter the submission ID: ")
            results = check_submission(submission_id)
            
            if "error" in results:
                print(f"\nError: {results['error']}")
            else:
                print(f"\nStatus: {results['status']}")
                if results['status'] == "done":
                    if SAVE_MODE in [2, 3] and 'similarity_index' in results:
                        print(f"Similarity Index: {results['similarity_index']}")
                    if SAVE_MODE in [1, 3] and 'ai_index' in results:
                        print(f"AI Writing Index: {results['ai_index']}")
                    
                    if SAVE_MODE in [2, 3] and 'similarity_report_url' in results:
                        print(f"\nSimilarity Report Download Link (expires in 3 days):")
                        print(results['similarity_report_url'])
                    
                    if SAVE_MODE in [1, 3] and 'ai_report_url' in results:
                        print(f"\nAI Writing Report Download Link (expires in 3 days):")
                        print(results['ai_report_url'])
        
        elif choice == "3":
            # Check quota for all accounts
            print("\nChecking quota for all accounts...")
            quota_data = check_quota()
            
            for result in quota_data["accounts"]:
                print(f"Account {result['email']}: {result['quota']}")
            
            print(f"\n{quota_data['remaining']} Submissions Left Today")
        
        elif choice == "4":
            # Quit
            print("\nThank you for using ScopedLens Document Checker. Goodbye!")
            sys.exit(0)
        
        else:
            print("\nInvalid choice. Please enter 1-4.")

if __name__ == "__main__":
    main_menu()