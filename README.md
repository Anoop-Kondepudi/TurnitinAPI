# Turnitin API

API service for checking documents with Turnitin.

## ⚠️ Important Notice

**This project is no longer operational and has been archived for educational purposes.**

As part of making this repository publicly available, all production infrastructure has been decommissioned:
- Cloudflare R2 credentials have been rotated and deactivated
- Proxy services have been discontinued
- The public API endpoints are no longer functional

While a private API instance continues to serve Ryne AI, this codebase is provided as-is for reference and learning purposes only.

## Endpoints

- `POST /submit` - Submit a document URL for processing
- `GET /receive/{submission_id}` - Check status of a submission
- `GET /quota` - Check remaining quota

## Deployment

This application is designed to be deployed on Render.

### Environment Variables

None required for basic functionality.


### Usage: 

Here are the proper curl command templates for each endpoint in your API:

1. Submit a document

curl -X POST "https://turnitin.vercel.app/submit" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Code: ryne_ai" \
  -d '{"url": "https://example.com/path/to/document.pdf"}'

Response example:

{"submission_id": "12345678-1234-1234-1234-123456789abc"}

2. Check submission status

curl -X GET "https://turnitin.vercel.app/receive/{submission_id}" \
  -H "X-Auth-Code: ryne_ai"

Response examples:

- When loading:
{"status": "loading"}

- When complete:
{
  "status": "done",
  "ai_index": "85%",
  "ai_report_url": "https://example-cloudflare-url.com/path/to/report.pdf"
}

- When error:
{"status": "error", "error": "Error message details"}

3. Check quota

curl -X GET "https://turnitin.vercel.app/quota" \
  -H "X-Auth-Code: ryne_ai"

Response example:

{"remaining": 42}