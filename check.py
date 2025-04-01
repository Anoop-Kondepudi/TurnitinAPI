import httpx
import time
import argparse
from bs4 import BeautifulSoup
from cloudflare_utils import upload_to_cloudflare, init_cloudflare_client, R2_BUCKET_NAME
from account_manager import get_account_for_upload, get_all_accounts, get_account_by_email

# Proxy settings (reused from backend.py)
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

def check_all_accounts():
    """Check plan pages for all accounts"""
    print("Checking plan pages for all accounts...")
    all_accounts = get_all_accounts()
    results = []
    
    for account in all_accounts:
        result = check_plan_page_for_account(account)
        results.append(result)
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Check ScopedLens plan pages')
    parser.add_argument('--email', help='Specific email to check (optional)')
    args = parser.parse_args()
    
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