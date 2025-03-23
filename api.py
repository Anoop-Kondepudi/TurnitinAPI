from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any
import uvicorn
import os
from datetime import datetime
import uuid
import re
import os.path
import urllib.parse

# Import functions from existing scripts
from backend import download_file, upload_document, check_submission, check_quota as check_all_quotas, TMP_DIR

app = FastAPI(
    title="Turnitin API",
    description="API for checking documents with Turnitin",
    version="1.0.0"
)

# Models for request/response - updated
class SubmitRequest(BaseModel):
    url: HttpUrl

class SubmitResponse(BaseModel):
    submission_id: str

class StatusResponse(BaseModel):
    status: str
    ai_index: Optional[str] = None
    ai_report_url: Optional[str] = None
    error: Optional[str] = None

class AccountQuota(BaseModel):
    email: str
    quota: str
    debug_url: Optional[str] = None

class QuotaResponse(BaseModel):
    remaining: int
    accounts: Optional[List[AccountQuota]] = None
    total_used: Optional[int] = None
    total_limit: Optional[int] = None
    debug_urls: Optional[List[Dict[str, str]]] = None

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
    
    # Ensure temp_filename is in /tmp directory
    temp_filepath = os.path.join(TMP_DIR, temp_filename)
    
    try:
        # Download the file to /tmp directory
        local_file = download_file(str(request.url), temp_filepath)
        
        if not local_file:
            raise HTTPException(status_code=400, detail="Failed to download file from URL")
        
        # Upload to Turnitin
        submission_id = upload_document(local_file)
        
        # Clean up the temporary file
        if os.path.exists(local_file):
            os.remove(local_file)
        
        if not submission_id:
            raise HTTPException(status_code=500, detail="Failed to get submission ID from Tunrnitin")
        
        # Return only the submission ID
        return {"submission_id": submission_id}
    
    except Exception as e:
        # Clean up in case of error
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
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
                
            # Use the correct key for AI report URL
            if "ai_report_url" in results:
                response["ai_report_url"] = results["ai_report_url"]
                
            return response
        
        # Default fallback
        return {"status": results["status"]}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/quota", response_model=QuotaResponse)
async def get_quota(include_debug: bool = False):
    """Check remaining quota across all accounts"""
    try:
        quota_data = check_all_quotas()
        
        # Include full debug information if requested
        if include_debug:
            return quota_data
        else:
            # Return only the remaining field
            return {"remaining": quota_data["remaining"]}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking quota: {str(e)}")

# Root endpoint with API info remains the same
@app.get("/")
async def root():
    return {
        "name": "Turnitin API",
        "version": "1.0.0",
        "endpoints": {
            "POST /submit": "Submit a document URL for processing",
            "GET /receive/{submission_id}": "Check status of a submission",
            "GET /quota": "Check remaining quota (add ?include_debug=true for detailed info)"
        }
    }

# Run the API server when the script is executed directly
if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)