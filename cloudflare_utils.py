import boto3
from botocore.config import Config
import json
import os
from datetime import datetime, timedelta

# Cloudflare R2 configuration
R2_BUCKET_NAME = "files"  # Replace with your actual bucket name

def init_cloudflare_client():
    """Initialize Cloudflare R2 client""" #MCBatmanGamingHere@gmail.com
    # CLOUDFLARE R2 CREDENTIALS HAVE BEEN ROLLED, SO BELOW CREDS ARE INVALID FOR SECURITY PURPOSES.
    return boto3.client(
        service_name='s3',
        endpoint_url='https://12cc55b238850cafc5209601b58df058.r2.cloudflarestorage.com',
        aws_access_key_id='aeef10594dbb8270dd5ac172d0f7d97e',
        aws_secret_access_key='cd6e745d23d455579f50bc04974c0930ce576cc8cc8eb8d522fd2001e043b3b9',
        config=Config(signature_version='v4')
    )

def upload_to_cloudflare(file_path, object_name):
    """Upload file to Cloudflare R2 and return presigned URL"""
    client = init_cloudflare_client()
    
    try:
        # Get the filename for the Content-Disposition header
        filename = os.path.basename(file_path)
        
        with open(file_path, 'rb') as file_data:
            client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=object_name,
                Body=file_data,
                ContentType='application/pdf',
                ContentDisposition=f'attachment; filename="{filename}"'
            )
        
        # Generate presigned URL that expires in 3 days
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': R2_BUCKET_NAME,
                'Key': object_name,
                'ResponseContentDisposition': f'attachment; filename="{filename}"'
            },
            ExpiresIn=3*24*60*60  # 3 days in seconds
        )
        return url
    except Exception as e:
        print(f"Error uploading to Cloudflare: {str(e)}")
        return None