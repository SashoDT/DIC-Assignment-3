import os
import json
import boto3
print("IMPORT PROFANITY FILTER")
from profanityfilter import ProfanityFilter

# Get the cleaned and output bucket names from SSM
endpoint_url = os.environ.get("AWS_ENDPOINT_URL") or ("http://" + os.environ.get("LOCALSTACK_HOSTNAME", "localhost") + ":4566")

s3 = boto3.client("s3", endpoint_url=endpoint_url)
ssm = boto3.client("ssm", endpoint_url=endpoint_url)

cleaned_bucket = ssm.get_parameter(Name="/dic/cleaned_bucket")["Parameter"]["Value"]
presentiment_bucket = ssm.get_parameter(Name="/dic/presentiment_bucket")["Parameter"]["Value"]

# Create profanity filter 
print("CREATE PROFANITY FILTER")
pf = ProfanityFilter()

def handler(event, context):
    print("START HANDLER")
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        obj = s3.get_object(Bucket=bucket, Key=key)
        raw_data = obj["Body"].read().decode("utf-8")

        processed_lines = []

        # Check profanity in each relevant field
        print("START 2nd FORLOOP")
        for line in raw_data.strip().splitlines():
            if not line.strip():
                continue
            try:
                review = json.loads(line)
                flagged = False

                print("Start 3rd FORLOOP")
                for field in ["reviewText", "summary", "overall"]:
                    tokens = review.get(field, [])
                    text = " ".join(tokens) if isinstance(tokens, list) else str(tokens)
                    if pf.is_profane(text):
                        flagged = True
                        break

                review["has_profanity"] = flagged
                processed_lines.append(json.dumps(review))
            except json.JSONDecodeError:
                continue  # Skip bad lines

        # Put result in next bucket
        print("Put into Bucket")
        s3.put_object(
            Bucket=presentiment_bucket,
            Key=key,
            Body="\n".join(processed_lines).encode("utf-8") # Join all lines back together 
        )
