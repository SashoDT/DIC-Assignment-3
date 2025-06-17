import os
import json
import boto3

# Get the cleaned and output bucket names from SSM
endpoint_url = os.environ.get("AWS_ENDPOINT_URL") or ("http://" + os.environ.get("LOCALSTACK_HOSTNAME", "localhost") + ":4566")

s3 = boto3.client("s3", endpoint_url=endpoint_url)
ssm = boto3.client("ssm", endpoint_url=endpoint_url)

cleaned_bucket = ssm.get_parameter(Name="/dic/cleaned_bucket")["Parameter"]["Value"]
presentiment_bucket = ssm.get_parameter(Name="/dic/presentiment_bucket")["Parameter"]["Value"]

# Load bad words from file
with open("bad-words.txt", "r") as f:
    bad_words1 = set(line.strip().lower() for line in f if line.strip())

# Load bad words from profanityfilter package: 
with open("badwords_profanityfilter.txt", "r") as f:
    bad_words2 = set(line.strip().lower() for line in f if line.strip())

bad_words = bad_words1.union(bad_words2)

# Create profanity filter 
def contains_profanity(text):
    #text = text.translate(str.maketrans("", "", string.punctuation)).lower()
    #words = text.split()
    # text is a list of words now
    return any(word in bad_words for word in text)

def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        obj = s3.get_object(Bucket=bucket, Key=key)
        raw_data = obj["Body"].read().decode("utf-8")

        processed_lines = []

        # Check profanity in each relevant field
        for line in raw_data.strip().splitlines():
            if not line.strip():
                continue
            try:
                review = json.loads(line)
                flagged = False
                for field in ["reviewText", "summary"]: 
                    tokens = review.get(field, [])
                    if isinstance(tokens, list) and contains_profanity(tokens):
                        flagged = True
                        break
                review["has_profanity"] = flagged
                processed_lines.append(json.dumps(review))
            except json.JSONDecodeError:
                continue  # Skip bad lines

        # Put result in next bucket
        s3.put_object(
            Bucket=presentiment_bucket,
            Key=key,
            Body="\n".join(processed_lines).encode("utf-8") # Join all lines back together 
        )

    return {"status": "OK"}

