import httpx
import os
import re
import time
from bs4 import BeautifulSoup
from datetime import datetime
import urllib.parse
import sys
import json
import uuid
from cloudflare_utils import upload_to_cloudflare, init_cloudflare_client, R2_BUCKET_NAME
from account_manager import get_account_for_upload, get_account_for_submission, get_all_accounts

# Proxy settings
PROXY_HOST = "144.229.117.13"
PROXY_PORT = "1337"
PROXY_USERNAME = "lho7SIZFaRh9"
PROXY_PASSWORD = "1inYc0RRMvYs"

# Configure proxy URL
PROXY_URL = f"http://{PROXY_USERNAME}:{PROXY_PASSWORD}@{PROXY_HOST}:{PROXY_PORT}"

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
SAVE_MODE = 3  # 1 = AI only, 2 = Similarity only, 3 = Both

# Add a constant for temp directory
TMP_DIR = "/tmp"  # Use Vercel's tmp directory for serverless functions

def download_file(url, local_filename=None):
    """Download a file from a URL and save it locally in the /tmp directory"""
    if not local_filename:
        local_filename = os.path.basename(urllib.parse.urlparse(url).path)
        if not local_filename:
            local_filename = "downloaded_file"
    
    # Ensure the file is saved to the /tmp directory
    local_filename = os.path.join(TMP_DIR, os.path.basename(local_filename))
    
    print(f"Downloading file from {url} to {local_filename}...")
    
    try:
        transport = httpx.HTTPTransport(proxy=PROXY_URL)
        with httpx.Client(transport=transport) as client:
            response = client.get(url)
            response.raise_for_status()
            
            with open(local_filename, 'wb') as f:
                f.write(response.content)
        
        print(f"File downloaded successfully to {local_filename}")
        return local_filename
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
        # Create a client with explicit decompression and timeout settings
        transport = httpx.HTTPTransport(
            proxy=PROXY_URL,
            retries=3
        )
        
        with httpx.Client(
            cookies=cookies, 
            headers=HEADERS, 
            transport=transport,
            timeout=30.0,  # Increase timeout
            follow_redirects=True  # Follow redirects automatically
        ) as client:
            # Explicitly set Accept-Encoding to handle compression properly
            headers_with_encoding = HEADERS.copy()
            headers_with_encoding["Accept-Encoding"] = "gzip, deflate"
            
            create_response = client.get(create_url, headers=headers_with_encoding)
            
            # Force encoding to UTF-8 if needed
            create_response.encoding = "utf-8"
            
            # Get the decoded content
            html_content = create_response.text
            
            # Save HTML for debugging
            debug_url = save_debug_html(html_content, f"upload_{account['email']}")
            print(f"DEBUG HTML for upload: {debug_url}")
            
            # Parse the HTML to extract the CSRF token
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find CSRF token - try the form first
            csrf_token = None
            submission_form = soup.find('form', {'id': 'submission-form'})
            if submission_form:
                csrf_input = submission_form.find('input', {'name': 'csrfmiddlewaretoken'})
                if csrf_input:
                    csrf_token = csrf_input.get('value')
                    print(f"Found CSRF token in submission form: {csrf_token[:10]}...")
            
            # If not found, try a more general approach
            if not csrf_token:
                csrf_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
                if csrf_input:
                    csrf_token = csrf_input.get('value')
                    print(f"Found CSRF token with general selector: {csrf_token[:10]}...")
            
            # If still not found, save debug info and return None
            if not csrf_token:
                print(f"CSRF token not found. Debug HTML already saved: {debug_url}")
                
                # Check if we're logged in or redirected to login page
                if "login" in html_content.lower() or "sign in" in html_content.lower():
                    print("Session may have expired - user not logged in")
                else:
                    # Print form elements for debugging
                    forms = soup.find_all('form')
                    print(f"Found {len(forms)} forms on the page")
                    for i, form in enumerate(forms):
                        print(f"Form {i+1} ID: {form.get('id', 'No ID')}")
                        inputs = form.find_all('input')
                        print(f"  Found {len(inputs)} inputs in this form")
                        for input_elem in inputs:
                            print(f"  Input: name={input_elem.get('name', 'No name')}, type={input_elem.get('type', 'No type')}")
                
                print("Could not find CSRF token on the page")
                return None
            
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
            upload_headers = headers_with_encoding.copy()
            upload_headers["Referer"] = create_url
            
            # Make the POST request to upload the document
            with open(file_path, 'rb') as f:
                files = {"upload_document": (file_name, f, 'application/octet-stream')}
                upload_response = client.post(
                    create_url,
                    headers=upload_headers,
                    data=form_data,
                    files=files,
                    timeout=60.0  # Longer timeout for upload
                )
            
            # Check if the upload was successful
            if upload_response.status_code == 200 or upload_response.status_code == 302:
                # The upload was successful, now we need to get the submission ID
                # We'll check the submissions page to find the most recent submission
                print("Upload appears successful, retrieving submission ID...")
                time.sleep(3)  # Wait a bit more for the server to process the upload
                
                submissions_url = "https://scopedlens.com/self-service/submissions/"
                
                # Use the same robust HTTP client configuration for submissions page
                try:
                    # Get submissions page with the same robust approach
                    submissions_response = client.get(
                        submissions_url,
                        headers=headers_with_encoding,
                        timeout=30.0,
                        follow_redirects=True
                    )
                    
                    # Force encoding to UTF-8 if needed
                    submissions_response.encoding = "utf-8"
                    
                    # Get the decoded content
                    submissions_html = submissions_response.text
                    
                    # Always save HTML for debugging regardless of success
                    debug_url = save_debug_html(submissions_html, f"submissions_page_{account['email']}")
                    print(f"Submissions page debug HTML: {debug_url}")
                    
                    if submissions_response.status_code == 200:
                        # Parse the HTML to find the most recent submission
                        submissions_soup = BeautifulSoup(submissions_html, 'html.parser')
                        
                        # First try the expected selector
                        submission_link = submissions_soup.select_one('#submission-row td:first-child a')
                        
                        # If not found, try more general approaches
                        if not submission_link:
                            print("First selector failed, trying alternate selectors...")
                            # Try to find the first link in the first row of the submissions table
                            submission_tables = submissions_soup.select('table.table')
                            if submission_tables:
                                first_table = submission_tables[0]
                                rows = first_table.select('tbody tr')
                                if rows:
                                    first_row = rows[0]
                                    # Try to find the first anchor in the first row
                                    submission_link = first_row.find('a')
                                    if submission_link:
                                        print("Found submission link using alternate selector")
                        
                        # If we found a link
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
                            
                            # Print more detailed debugging information
                            print("Page structure analysis:")
                            tables = submissions_soup.find_all('table')
                            print(f"Found {len(tables)} tables on page")
                            
                            for i, table in enumerate(tables):
                                print(f"Table {i+1} class: {table.get('class', 'No class')}")
                                rows = table.find_all('tr')
                                print(f"  Found {len(rows)} rows in this table")
                                if rows:
                                    for j, row in enumerate(rows[:2]):  # Print info about first 2 rows only
                                        links = row.find_all('a')
                                        print(f"  Row {j+1} has {len(links)} links")
                                        for k, link in enumerate(links):
                                            print(f"    Link {k+1} href: {link.get('href', 'No href')}")
                    else:
                        print(f"Failed to retrieve submissions list. Status code: {submissions_response.status_code}")
                        print(f"Response content: {submissions_html[:500]}...")
                
                except Exception as e:
                    print(f"Error retrieving submissions page: {str(e)}")
                    # Try one more time with a longer delay
                    print("Retrying after a longer delay...")
                    time.sleep(7)  # Wait longer before retry
                    try:
                        submissions_response = client.get(
                            submissions_url,
                            headers=headers_with_encoding,
                            timeout=45.0,  # Even longer timeout for retry
                            follow_redirects=True
                        )
                        
                        if submissions_response.status_code == 200:
                            submissions_soup = BeautifulSoup(submissions_response.text, 'html.parser')
                            submission_link = submissions_soup.select_one('table.table tbody tr:first-child a')
                            
                            if submission_link:
                                href = submission_link.get('href')
                                submission_id = href.split('/')[-1]
                                
                                # Associate submission with account
                                from account_manager import associate_submission_with_account
                                associate_submission_with_account(submission_id, account["email"])
                                
                                print(f"Document uploaded successfully on retry! Submission ID: {submission_id}")
                                return submission_id
                            else:
                                print("Still could not find submission ID after retry")
                                debug_url = save_debug_html(submissions_response.text, f"submissions_retry_{account['email']}")
                                print(f"Retry submissions debug HTML: {debug_url}")
                    except Exception as retry_e:
                        print(f"Retry also failed: {str(retry_e)}")
            
            return None
    
    except httpx.HTTPStatusError as e:
        print(f"HTTP error during upload: {e.response.status_code}")
        print(f"Response content: {e.response.text[:500]}...")
        # Save debug HTML for HTTP error
        debug_url = save_debug_html(e.response.text, f"http_error_{account['email']}")
        print(f"HTTP error debug HTML: {debug_url}")
        return None
    except httpx.RequestError as e:
        print(f"Request error during upload: {str(e)}")
        return None
    except Exception as e:
        print(f"An error occurred during upload: {str(e)}")
        return None

def check_submission(submission_id, temp_dir=None):
    """Check the status of a submission and return the indices and report links"""
    print(f"Checking submission: {submission_id}")
    
    # Use provided temp_dir or create a default one
    if temp_dir is None:
        temp_dir = os.path.join(TMP_DIR, f'Reports_{submission_id}_{uuid.uuid4().hex}')
        os.makedirs(temp_dir, exist_ok=True)
    
    # Get the account associated with this submission
    try:
        from account_manager import get_submission_to_account_map
        submission_account_map = get_submission_to_account_map()
        
        # First try to get the account directly associated with this submission
        if submission_id in submission_account_map:
            account_email = submission_account_map[submission_id]["account_email"]
            print(f"Found associated account: {account_email} for submission: {submission_id}")
            account = get_account_for_submission(submission_id)
            if account["email"] != account_email:
                print(f"WARNING: Account mismatch! Map says: {account_email}, got: {account['email']}")
                # Try to get the account by email instead
                from account_manager import get_account_by_email
                corrected_account = get_account_by_email(account_email)
                if corrected_account:
                    account = corrected_account
                    print(f"Corrected to use account: {account['email']}")
        else:
            print(f"No account mapping found for submission: {submission_id}")
            account = get_account_for_submission(submission_id)
    except Exception as e:
        print(f"Error retrieving account mapping: {str(e)}")
        account = get_account_for_submission(submission_id)
    
    cookies = account["cookies"]
    print(f"Using account: {account['email']}")
    
    submission_url = f"https://scopedlens.com/self-service/submission/{submission_id}"
    
    try:
        # Create a client with explicit decompression and timeout settings
        transport = httpx.HTTPTransport(
            proxy=PROXY_URL,
            retries=3
        )
        
        with httpx.Client(
            cookies=cookies, 
            headers=HEADERS, 
            transport=transport,
            timeout=30.0,  # Increase timeout
            follow_redirects=True  # Follow redirects automatically
        ) as client:
            # Explicitly set Accept-Encoding to handle compression properly
            headers_with_encoding = HEADERS.copy()
            headers_with_encoding["Accept-Encoding"] = "gzip, deflate"
            
            submission_response = client.get(
                submission_url,
                headers=headers_with_encoding
            )
            
            # Force encoding to UTF-8 if needed
            submission_response.encoding = "utf-8"
            
            # Get the decoded content
            html_content = submission_response.text
            
            # Save HTML for debugging
            debug_url = save_debug_html(html_content, f"submission_{submission_id}_{account['email']}")
            print(f"DEBUG HTML for submission check: {debug_url}")
            
            if submission_response.status_code == 200:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Check for "Page not found" error
                error_text = soup.find('h1')
                if error_text and error_text.text.strip() == "Page not found":
                    return {"error": "Invalid submission_id"}
                
                # Check for error message in the table
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
                            # Update regex to also match asterisk (*) as a valid value
                            ai_match = re.search(r'([*\d]+)\s*%', ai_text)
                            if ai_match:
                                results['ai_index'] = ai_match.group(1) + '%'
                                if SAVE_MODE == 1:
                                    has_required_index = True
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Process reports based on SAVE_MODE
                if SAVE_MODE in [2, 3]:
                    similarity_link = soup.find('a', string=re.compile("Download Similarity Report"))
                    if similarity_link:
                        href = similarity_link.get('href')
                        print(f"Found similarity report link: {href}")
                        local_path = os.path.join(temp_dir, f"similarity_report_{timestamp}.pdf")
                        try:
                            # Use the same robust client to download the report
                            response = client.get(
                                href, 
                                headers=headers_with_encoding,
                                timeout=60.0  # Longer timeout for downloading reports
                            )
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
                            else:
                                print(f"Failed to download similarity report: HTTP {response.status_code}")
                        except Exception as e:
                            print(f"Error downloading similarity report: {str(e)}")
                
                if SAVE_MODE in [1, 3]:
                    ai_link = soup.find('a', string=re.compile("Download AI Writing Report"))
                    if ai_link:
                        href = ai_link.get('href')
                        print(f"Found AI report link: {href}")
                        local_path = os.path.join(temp_dir, f"ai_report_{timestamp}.pdf")
                        try:
                            # Use the same robust client to download the report
                            response = client.get(
                                href,
                                headers=headers_with_encoding,
                                timeout=60.0  # Longer timeout for downloading reports
                            )
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
                            else:
                                print(f"Failed to download AI report: HTTP {response.status_code}")
                        except Exception as e:
                            print(f"Error downloading AI report: {str(e)}")
                
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
                
                # Filter out None values before returning
                results = {k: v for k, v in results.items() if v is not None}
                
                # No need to save results to JSON anymore
                return results
                
            else:
                error_message = f"HTTP Error: {submission_response.status_code}"
                print(error_message)
                print(f"Response content: {html_content[:500]}...")
                return {"error": error_message}
    
    except httpx.HTTPStatusError as e:
        error_message = f"HTTP status error checking submission: {e.response.status_code}"
        print(error_message)
        print(f"Response content: {e.response.text[:500]}...")
        # Save debug HTML for HTTP error
        debug_url = save_debug_html(e.response.text, f"submission_http_error_{submission_id}")
        print(f"HTTP error debug HTML: {debug_url}")
        return {"error": error_message}
    except httpx.RequestError as e:
        error_message = f"Request error checking submission: {str(e)}"
        print(error_message)
        return {"error": error_message}
    except Exception as e:
        error_message = f"Error checking submission: {str(e)}"
        print(error_message)
        return {"error": error_message}

def download_reports(submission_id, results):
    """Download the reports for a submission to /tmp directory"""
    # Get the account associated with this submission
    account = get_account_for_submission(submission_id)
    cookies = account["cookies"]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    transport = httpx.HTTPTransport(proxy=PROXY_URL)
    with httpx.Client(cookies=cookies, headers=HEADERS, transport=transport) as client:
        if 'similarity_report_url' in results and results["similarity_report_url"]:
            try:
                similarity_report_response = client.get(results["similarity_report_url"])
                if similarity_report_response.status_code == 200:
                    similarity_report_filename = os.path.join(TMP_DIR, f"similarity_report_{submission_id}_{timestamp}.pdf")
                    with open(similarity_report_filename, "wb") as file:
                        file.write(similarity_report_response.content)
                    print(f"Similarity Report downloaded to: {os.path.abspath(similarity_report_filename)}")
                else:
                    print(f"Failed to download Similarity Report. Status code: {similarity_report_response.status_code}")
            except Exception as e:
                print(f"Error downloading Similarity Report: {str(e)}")
        else:
            print("Similarity Report URL not available")
        
        if 'ai_report_url' in results and results["ai_report_url"]:
            try:
                ai_report_response = client.get(results["ai_report_url"])
                if ai_report_response.status_code == 200:
                    ai_report_filename = os.path.join(TMP_DIR, f"ai_writing_report_{submission_id}_{timestamp}.pdf")
                    with open(ai_report_filename, "wb") as file:
                        file.write(ai_report_response.content)
                    print(f"AI Writing Report downloaded to: {os.path.abspath(ai_report_filename)}")
                else:
                    print(f"Failed to download AI Writing Report. Status code: {ai_report_response.status_code}")
            except Exception as e:
                print(f"Error downloading AI Writing Report: {str(e)}")
        else:
            print("AI Writing Report URL not available")

# Update the check_quota function

def check_quota():
    """Check the remaining quota from ScopedLens for all accounts"""
    create_url = "https://scopedlens.com/self-service/submission/create"
    all_accounts = get_all_accounts()
    
    quota_results = []
    total_used = 0
    total_limit = 0
    debug_urls = []
    
    for account in all_accounts:
        try:
            cookies = account["cookies"]
            
            # Create a client with explicit decompression and timeout settings
            transport = httpx.HTTPTransport(
                proxy=PROXY_URL,
                retries=3
            )
            
            with httpx.Client(
                cookies=cookies, 
                headers=HEADERS, 
                transport=transport,
                timeout=30.0,  # Increase timeout
                follow_redirects=True  # Follow redirects automatically
            ) as client:
                # Explicitly set Accept-Encoding to handle compression properly
                headers_with_encoding = HEADERS.copy()
                headers_with_encoding["Accept-Encoding"] = "gzip, deflate"
                
                response = client.get(create_url, headers=headers_with_encoding)
                
                # Force encoding to UTF-8 if needed
                response.encoding = "utf-8"
                
                # Get the decoded content
                html_content = response.text
                
                # Save HTML for debugging
                debug_url = save_debug_html(html_content, account["email"])
                if debug_url:
                    debug_urls.append({"email": account["email"], "debug_url": debug_url})
                    print(f"DEBUG HTML for {account['email']}: {debug_url}")
                
                if response.status_code == 200:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Print the first 500 characters of HTML for debugging
                    print(f"DEBUG HTML preview: {html_content[:500]}")
                    
                    quota_element = soup.select_one("div > div > div > h6")
                    if quota_element:
                        # Get the text and replace all whitespace (including newlines) with single spaces
                        quota_text = re.sub(r'\s+', ' ', quota_element.text.strip())
                        print(f"DEBUG Raw quota text for {account['email']}: '{quota_text}'")
                        
                        # Extract the numbers using regex
                        quota_match = re.search(r'(\d+)\s*/\s*(\d+)', quota_text)
                        if quota_match:
                            used = int(quota_match.group(1))
                            limit = int(quota_match.group(2))
                            total_used += used
                            total_limit += limit
                            # Format as a single string without extra spaces
                            quota = f"{used}/{limit}"
                        else:
                            # Simple cleanup as fallback
                            clean_text = quota_text.replace("Your Quota:", "").replace("Reset everyday", "").strip()
                            # Further replace any remaining newlines
                            quota = clean_text.replace("\n", "")
                            print(f"WARNING: Could not extract numbers from '{quota_text}' for {account['email']}")
                    else:
                        quota = "Quota information not found"
                        print(f"WARNING: Quota element not found for {account['email']}")
                else:
                    quota = f"Error: Could not fetch quota (HTTP {response.status_code})"
                    
                quota_results.append({
                    "email": account["email"],
                    "quota": quota
                })
                
        except Exception as e:
            print(f"Exception for {account['email']}: {str(e)}")
            quota_results.append({
                "email": account["email"],
                "quota": f"Error: {str(e)}"
            })
    
    remaining_submissions = total_limit - total_used
    
    result = {
        "accounts": quota_results,
        "total_used": total_used,
        "total_limit": total_limit,
        "remaining": remaining_submissions,
        "debug_urls": debug_urls
    }
    
    print(f"DEBUG Final quota result: {json.dumps(result, indent=2)}")
    return result

def save_debug_html(html_content, identifier):
    """Save HTML content to Cloudflare R2 for debugging"""
    timestamp = int(time.time())
    object_name = f"debug/html_{identifier}_{timestamp}.html"
    
    client = init_cloudflare_client()
    
    try:
        client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=object_name,
            Body=html_content,
            ContentType='text/html'
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
                            if 'similarity_index' in results:
                                print(f"Similarity Index: {results['similarity_index']}")
                            if 'ai_index' in results:
                                print(f"AI Writing Index: {results['ai_index']}")
                            
                            # Fix key names for URLs
                            if "similarity_report_url" in results:
                                print(f"Similarity Report URL: {results['similarity_report_url']}")
                            else:
                                print("Similarity Report not available yet")
                            
                            if "ai_report_url" in results:
                                print(f"AI Writing Report URL: {results['ai_report_url']}")
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