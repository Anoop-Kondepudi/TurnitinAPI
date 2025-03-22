from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional
import uvicorn
import os
from datetime import datetime
import uuid
import re
import os.path
import urllib.parse
import logging
from account_manager import init_accounts

# Import functions from existing scripts
from backend import download_file, upload_document, check_submission, check_quota as check_all_quotas

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ScopedLens API",
    description="API for checking documents with ScopedLens",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Verify everything is working on startup"""
    logger.info("API starting up")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Directory contents: {os.listdir()}")
    
    # Test account initialization
    init_success = init_accounts()
    logger.info(f"Account initialization: {'Success' if init_success else 'Failed'}")
    
    # Test quota check
    try:
        from backend import check_quota
        quota_data = check_quota()
        logger.info(f"Initial quota check: {quota_data['remaining']} submissions remaining")
    except Exception as e:
        logger.error(f"Error during initial quota check: {str(e)}")

# Models for request/response - simplified
class SubmitRequest(BaseModel):
    url: HttpUrl

class SubmitResponse(BaseModel):
    submission_id: str

class StatusResponse(BaseModel):
    status: str
    ai_index: Optional[str] = None
    ai_report_url: Optional[str] = None
    error: Optional[str] = None

class QuotaResponse(BaseModel):
    remaining: int

# Endpoints
@app.post("/submit", response_model=SubmitResponse)
async def submit_document(request: SubmitRequest):
    """Submit a document for processing"""
    # Extract original filename from URL
    url_path = urllib.parse.urlparse(str(request.url)).path
    original_filename = os.path.basename(url_path)
    
    # Clean the original filename (remove query parameters if present)
    original_filename = re.sub(r'\?.*$', '', original_filename)
    
    # If no filename could be extracted or it's invalid, use a default
    if not original_filename or original_filename == '':
        original_filename = "document.pdf"
    
    # Generate a unique version by adding UUID as a suffix
    base_name, extension = os.path.splitext(original_filename)
    if not extension:
        extension = '.pdf'  # Default extension if none found
    
    # Use original filename with UUID suffix for uniqueness
    request_id = uuid.uuid4()
    temp_filename = f"{base_name}_{request_id}{extension}"
    
    try:
        # Download the file
        local_file = download_file(str(request.url), temp_filename)
        
        if not local_file:
            raise HTTPException(status_code=400, detail="Failed to download file from URL")
        
        # Upload to ScopedLens
        submission_id = upload_document(local_file)
        
        # Clean up the temporary file
        if os.path.exists(local_file):
            os.remove(local_file)
        
        if not submission_id:
            raise HTTPException(status_code=500, detail="Failed to get submission ID from ScopedLens")
        
        # Return only the submission ID
        return {"submission_id": submission_id}
    
    except Exception as e:
        # Clean up in case of error
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        raise HTTPException(status_code=500, detail=f"Error processing submission: {str(e)}")

@app.get("/receive/{submission_id}")
async def get_submission_status(submission_id: str):
    """Check the status of a submission"""
    try:
        # Get the submission results
        results = check_submission(submission_id)
        
        # Handle error case
        if "error" in results:
            return {"status": "error", "error": results["error"]}
        
        # If status is loading, return just that
        if results["status"] == "loading":
            return {"status": "loading"}
        
        # If status is done, return only the AI index and report URL
        if results["status"] == "done":
            response = {"status": "done"}
            
            if "ai_index" in results:
                response["ai_index"] = results["ai_index"]
                
            if "ai_report_url" in results:
                response["ai_report_url"] = results["ai_report_url"]
                
            return response
        
        # Default fallback
        return {"status": results["status"]}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/quota", response_model=QuotaResponse)
async def get_quota():
    """Check remaining quota across all accounts"""
    try:
        quota_data = check_all_quotas()
        # Return only the remaining field
        return {"remaining": quota_data["remaining"]}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking quota: {str(e)}")

# Root endpoint with API info remains the same
@app.get("/")
async def root():
    return {
        "name": "ScopedLens API",
        "version": "1.0.0",
        "endpoints": {
            "POST /submit": "Submit a document URL for processing",
            "GET /receive/{submission_id}": "Check status of a submission",
            "GET /quota": "Check remaining quota"
        }
    }

# Run the API server when the script is executed directly
if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)