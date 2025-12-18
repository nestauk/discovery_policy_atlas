"""Simple script to download datasets from S3.

cd backend
uv run python testing/evals/screening/download_datasets.py
  
The script downloads all files from s3://discovery-policy-atlas/eval/datasets/screening/
to backend/testing/evals/screening/datasets/, preserving subfolder structure.

The adapter expects datasets in:
- datasets/CESmed/
- datasets/SYNERGY/
- datasets/Three_IE/
"""

import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BUCKET_NAME = "discovery-policy-atlas"
S3_PREFIX = "eval/datasets/screening/"


def download_datasets():
    """Download all files from S3 bucket prefix to datasets directory, preserving subfolder structure."""
    s3_client = boto3.client("s3")
    script_dir = Path(__file__).parent
    datasets_dir = script_dir / "datasets"

    try:
        logger.info(f"Listing objects in s3://{BUCKET_NAME}/{S3_PREFIX}")
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=BUCKET_NAME, Prefix=S3_PREFIX)

        downloaded_count = 0
        for page in pages:
            if "Contents" not in page:
                logger.warning(f"No objects found in s3://{BUCKET_NAME}/{S3_PREFIX}")
                continue

            for obj in page["Contents"]:
                s3_key = obj["Key"]
                if s3_key.endswith("/"):
                    continue

                local_filename = s3_key.replace(S3_PREFIX, "")
                local_path = datasets_dir / local_filename

                local_path.parent.mkdir(parents=True, exist_ok=True)

                logger.info(f"Downloading {s3_key} -> {local_path}")
                s3_client.download_file(BUCKET_NAME, s3_key, str(local_path))
                downloaded_count += 1

        logger.info(f"Downloaded {downloaded_count} file(s) to {datasets_dir}")

    except ClientError as e:
        logger.error(f"AWS error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error downloading datasets: {e}")
        raise


if __name__ == "__main__":
    download_datasets()
