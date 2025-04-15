import httpx
import time
import argparse
import sys
from bs4 import BeautifulSoup
from cloudflare_utils import upload_to_cloudflare, init_cloudflare_client, R2_BUCKET_NAME
from account_manager import get_account_for_upload, get_all_accounts, get_account_by_email

# Proxy settings (reused from backend.py)
PROXY_HOST = "204.242.7.46"
PROXY_PORT = "1337"
PROXY_USERNAME = "G3Mvn9tOoCvL"
PROXY_PASSWORD = "7EldVMuIZl2s"

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

def check_plan_page_for_account(account):
    """Fetch the plan page for a specific account and save its HTML to Cloudflare"""
    print(f"\nFetching plan page for account: {account['email']}")
    
    cookies = account["cookies"]
    plan_url = "https://scopedlens.com/self-service/plan/"
    
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
            
            response = client.get(
                plan_url,
                headers=headers_with_encoding
            )
            
            # Force encoding to UTF-8 if needed
            response.encoding = "utf-8"
            
            # Get the decoded content
            html_content = response.text
            
            if response.status_code == 200:
                # Save HTML for debugging
                debug_url = save_debug_html(html_content, f"plan_page_{account['email']}")
                print(f"Plan page HTML saved. Debug URL: {debug_url}")
                
                # Parse the HTML to check for any errors or important information
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Check for error messages or important content
                error_messages = soup.find_all(class_=lambda x: x and 'error' in x.lower())
                if error_messages:
                    print("Found error messages on the page:")
                    for error in error_messages:
                        print(f"- {error.get_text(strip=True)}")
                
                return {
                    "email": account["email"],
                    "status": "success",
                    "debug_url": debug_url,
                    "has_errors": bool(error_messages)
                }
            else:
                error_message = f"HTTP Error: {response.status_code}"
                print(error_message)
                print(f"Response content: {html_content[:500]}...")
                return {
                    "email": account["email"],
                    "status": "error",
                    "error": error_message
                }
    
    except httpx.HTTPStatusError as e:
        error_message = f"HTTP status error: {e.response.status_code}"
        print(error_message)
        print(f"Response content: {e.response.text[:500]}...")
        return {
            "email": account["email"],
            "status": "error",
            "error": error_message
        }
    except httpx.RequestError as e:
        error_message = f"Request error: {str(e)}"
        print(error_message)
        return {
            "email": account["email"],
            "status": "error",
            "error": error_message
        }
    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        return {
            "email": account["email"],
            "status": "error",
            "error": error_message
        }

def redeem_code_for_account(account, code):
    """Redeem a code for a specific account and save the result HTML to Cloudflare"""
    print(f"\nRedeeming code for account: {account['email']}")
    
    cookies = account["cookies"]
    
    # The activation code input is on the plan page
    plan_url = "https://scopedlens.com/self-service/plan/"
    
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
            
            # First, get the plan page
            print(f"Loading plan page: {plan_url}")
            response = client.get(
                plan_url,
                headers=headers_with_encoding
            )
            
            # Force encoding to UTF-8 if needed
            response.encoding = "utf-8"
            
            if response.status_code != 200:
                error_message = f"HTTP Error when loading plan page: {response.status_code}"
                print(error_message)
                return {
                    "email": account["email"],
                    "status": "error",
                    "error": error_message
                }
            
            # Get the html content from the response
            html_content = response.text
            
            # Save HTML for debugging the form
            debug_url = save_debug_html(html_content, f"plan_page_form_{account['email']}")
            print(f"Plan page HTML saved. Debug URL: {debug_url}")
            
            # Parse the HTML to analyze the form
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find the form for the activation code
            form = soup.find('form')
            if not form:
                error_message = "No form found on the plan page"
                print(error_message)
                return {
                    "email": account["email"],
                    "status": "error",
                    "error": error_message
                }
            
            print(f"Found form: action='{form.get('action', 'None')}', method='{form.get('method', 'POST')}'")
            
            # Get the form action URL (if present, otherwise use the current URL)
            form_action = form.get('action')
            submit_url = form_action if form_action else plan_url
            
            # Make sure the submit URL is absolute
            if submit_url.startswith('/'):
                submit_url = f"https://scopedlens.com{submit_url}"
            print(f"Will submit to URL: {submit_url}")
            
            # Get CSRF token if present
            csrf_token = None
            csrf_field = form.find('input', {'name': 'csrfmiddlewaretoken'})
            if csrf_field:
                csrf_token = csrf_field.get('value')
                print(f"Found CSRF token: {csrf_token[:10]}..." if csrf_token else "No CSRF token found")
            
            # Find the name of the activation code input field
            code_input = None
            for input_elem in form.find_all('input'):
                input_type = input_elem.get('type', '')
                input_name = input_elem.get('name', '')
                input_placeholder = input_elem.get('placeholder', '').lower()
                
                # Check if this is likely the activation code input
                if (input_type == 'text' and 
                    ('code' in input_name.lower() or 
                     'activation' in input_name.lower() or
                     'code' in input_placeholder or
                     'activation' in input_placeholder)):
                    code_input = input_elem
                    break
            
            if not code_input:
                # If we couldn't find it through name/placeholder, find the non-hidden text input
                text_inputs = form.find_all('input', {'type': 'text'})
                if text_inputs:
                    code_input = text_inputs[0]  # Use the first text input
            
            if not code_input:
                error_message = "Could not find activation code input field"
                print(error_message)
                return {
                    "email": account["email"],
                    "status": "error",
                    "error": error_message
                }
            
            code_field_name = code_input.get('name', '')
            print(f"Found activation code input field with name: '{code_field_name}'")
            
            # Prepare the form data
            form_data = {
                code_field_name: code
            }
            
            # Add CSRF token if found
            if csrf_token:
                form_data['csrfmiddlewaretoken'] = csrf_token
                headers_with_encoding['Referer'] = plan_url
            
            # Submit the form
            print(f"Submitting code: {code} to URL: {submit_url}")
            response = client.post(
                submit_url,
                headers=headers_with_encoding,
                data=form_data
            )
            
            # Force encoding to UTF-8 if needed
            response.encoding = "utf-8"
            
            # Get the decoded content from the response after submission
            html_content = response.text
            
            if response.status_code == 200 or response.status_code == 302:
                # Save HTML for debugging
                debug_url = save_debug_html(html_content, f"redeem_code_result_{account['email']}")
                print(f"Redeem code result HTML saved. Debug URL: {debug_url}")
                
                # Parse the HTML to check for any errors or important information
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Check for error messages or important content
                error_messages = soup.find_all(class_=lambda x: x and 'error' in x.lower())
                success_messages = soup.find_all(class_=lambda x: x and 'success' in x.lower())
                
                # Also look for alert boxes that might contain messages
                alerts = soup.find_all(class_=lambda x: x and 'alert' in x.lower())
                
                if error_messages:
                    print("Found error messages on the page:")
                    for error in error_messages:
                        print(f"- {error.get_text(strip=True)}")
                
                if success_messages:
                    print("Found success messages on the page:")
                    for success in success_messages:
                        print(f"- {success.get_text(strip=True)}")
                
                if alerts:
                    print("Found alert messages on the page:")
                    for alert in alerts:
                        print(f"- {alert.get_text(strip=True)}")
                
                return {
                    "email": account["email"],
                    "status": "success",
                    "debug_url": debug_url,
                    "has_errors": bool(error_messages),
                    "has_success": bool(success_messages)
                }
            else:
                error_message = f"HTTP Error after submission: {response.status_code}"
                print(error_message)
                print(f"Response content: {html_content[:500]}...")
                return {
                    "email": account["email"],
                    "status": "error",
                    "error": error_message
                }
    
    except httpx.HTTPStatusError as e:
        error_message = f"HTTP status error: {e.response.status_code}"
        print(error_message)
        return {
            "email": account["email"],
            "status": "error",
            "error": error_message
        }
    except httpx.RequestError as e:
        error_message = f"Request error: {str(e)}"
        print(error_message)
        return {
            "email": account["email"],
            "status": "error",
            "error": error_message
        }
    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(error_message)
        return {
            "email": account["email"],
            "status": "error",
            "error": error_message
        }

def check_all_accounts():
    """Check plan pages for all accounts"""
    print("Checking plan pages for all accounts...")
    all_accounts = get_all_accounts()
    results = []
    
    for account in all_accounts:
        result = check_plan_page_for_account(account)
        results.append(result)
    
    return results

def check_accounts_menu():
    """Display menu for checking accounts"""
    all_accounts = get_all_accounts()
    
    while True:
        print("\n=== Check Accounts Menu ===")
        print("0. Check All Accounts")
        
        # Display each account option
        for i, account in enumerate(all_accounts, 1):
            print(f"{i}. Check {account['email']}")
        
        print("B. Back to Main Menu")
        
        choice = input("Enter your choice: ").strip()
        
        if choice.lower() == 'b':
            break
        
        try:
            choice_num = int(choice)
            if choice_num == 0:
                # Check all accounts
                results = check_all_accounts()
                print("\nResults for all accounts:")
                for result in results:
                    print(f"\nAccount: {result['email']}")
                    print(f"Status: {result['status']}")
                    if result['status'] == 'success':
                        print(f"Debug URL: {result['debug_url']}")
                        print(f"Has errors: {result['has_errors']}")
                    else:
                        print(f"Error: {result['error']}")
            elif 1 <= choice_num <= len(all_accounts):
                # Check specific account
                account = all_accounts[choice_num - 1]
                result = check_plan_page_for_account(account)
                print("\nResult:")
                print(f"Account: {result['email']}")
                print(f"Status: {result['status']}")
                if result['status'] == 'success':
                    print(f"Debug URL: {result['debug_url']}")
                    print(f"Has errors: {result['has_errors']}")
                else:
                    print(f"Error: {result['error']}")
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def redeem_code_menu():
    """Display menu for redeeming codes"""
    all_accounts = get_all_accounts()
    
    while True:
        print("\n=== Redeem Code Menu ===")
        
        # Display each account option
        for i, account in enumerate(all_accounts, 1):
            print(f"{i}. {account['email']}")
        
        print("B. Back to Main Menu")
        
        choice = input("Enter your choice (account number): ").strip()
        
        if choice.lower() == 'b':
            break
        
        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(all_accounts):
                # Get selected account
                account = all_accounts[choice_num - 1]
                
                # Ask for redemption code
                code = input(f"Enter redemption code for {account['email']}: ").strip()
                
                if code:
                    # Redeem the code
                    result = redeem_code_for_account(account, code)
                    print("\nRedemption Result:")
                    print(f"Account: {result['email']}")
                    print(f"Status: {result['status']}")
                    if result['status'] == 'success':
                        print(f"Debug URL: {result['debug_url']}")
                        if 'has_errors' in result:
                            print(f"Has errors: {result['has_errors']}")
                        if 'has_success' in result:
                            print(f"Has success: {result['has_success']}")
                    else:
                        print(f"Error: {result['error']}")
                else:
                    print("No code entered. Redemption cancelled.")
            else:
                print("Invalid account number. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def interactive_console():
    """Run the interactive console with the main menu"""
    print("\n=== ScopedLens Account Manager ===")
    
    while True:
        print("\nMain Menu:")
        print("1. Check Accounts")
        print("2. Redeem Code")
        print("3. Quit")
        
        choice = input("Enter your choice: ").strip()
        
        if choice == '1':
            check_accounts_menu()
        elif choice == '2':
            redeem_code_menu()
        elif choice == '3':
            print("Exiting program. Goodbye!")
            sys.exit(0)
        else:
            print("Invalid choice. Please try again.")

def main():
    parser = argparse.ArgumentParser(description='ScopedLens Account Manager')
    parser.add_argument('--interactive', action='store_true', help='Run in interactive mode')
    parser.add_argument('--email', help='Specific email to check (legacy mode)')
    args = parser.parse_args()
    
    # Default to interactive mode if no arguments are passed
    if len(sys.argv) == 1 or args.interactive:
        interactive_console()
        return
    
    # Legacy mode for backward compatibility
    if args.email:
        # Check specific account
        account = get_account_by_email(args.email)
        if not account:
            print(f"Error: Account not found for email: {args.email}")
            return
        
        result = check_plan_page_for_account(account)
        print("\nResult:", result)
    else:
        # Check all accounts
        results = check_all_accounts()
        print("\nResults for all accounts:")
        for result in results:
            print(f"\nAccount: {result['email']}")
            print(f"Status: {result['status']}")
            if result['status'] == 'success':
                print(f"Debug URL: {result['debug_url']}")
                print(f"Has errors: {result['has_errors']}")
            else:
                print(f"Error: {result['error']}")

if __name__ == "__main__":
    main() 