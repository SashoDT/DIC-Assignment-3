import os
import json
import string

import boto3

# Get the cleaned and output bucket names from SSM
endpoint_url = os.environ.get("AWS_ENDPOINT_URL") or ("http://" + os.environ.get("LOCALSTACK_HOSTNAME", "localhost") + ":4566")

s3 = boto3.client("s3", endpoint_url=endpoint_url)
ssm = boto3.client("ssm", endpoint_url=endpoint_url)

cleaned_bucket = ssm.get_parameter(Name="/dic/cleaned_bucket")["Parameter"]["Value"]
output_bucket = ssm.get_parameter(Name="/dic/output_bucket")["Parameter"]["Value"]

# Load bad words from file
with open("bad-words.txt", "r") as f:
    bad_words = set(line.strip().lower() for line in f if line.strip())

def contains_profanity(text):
    text = text.translate(str.maketrans("", "", string.punctuation)).lower()
    words = text.split()
    return any(word in bad_words for word in words)

def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        obj = s3.get_object(Bucket=bucket, Key=key)
        review = json.loads(obj["Body"].read().decode("utf-8"))

        flagged = False

        # Check profanity in each relevant field
        for field in ["reviewText", "summary", "overall"]:
            # Lowercase just in case again
            content = str(review.get(field, "")).lower()
            if contains_profanity(content):
                flagged = True
                break

        review["has_profanity"] = flagged

        # Save result to output bucket
        s3.put_object(
            Bucket=output_bucket,
            Key=key,
            Body=json.dumps(review).encode("utf-8")
        )
