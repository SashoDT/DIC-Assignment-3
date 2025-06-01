import json
import os
import string

# Load stopwords from file once at startup
with open(os.path.join(os.path.dirname(__file__), "stopwords.txt"), "r", encoding="utf-8") as f:
    STOPWORDS = set(word.strip().lower() for word in f if word.strip())

def preprocess_text(text):
    # Lowercase and remove punctuation
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    # Tokenize (simple whitespace split), remove stopwords
    tokens = [word for word in text.split() if word not in STOPWORDS]
    return " ".join(tokens)

def handler(event, context):
    for record in event["Records"]:
        # Read JSON from S3 (as string body)
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        import boto3
        s3 = boto3.client("s3", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))

        obj = s3.get_object(Bucket=bucket, Key=key)
        raw_data = obj["Body"].read().decode("utf-8")
        json_data = json.loads(raw_data)

        # Preprocess only these fields
        if "reviewText" in json_data:
            json_data["reviewText"] = preprocess_text(json_data["reviewText"])
        if "summary" in json_data:
            json_data["summary"] = preprocess_text(json_data["summary"])

        # Save to output bucket (same filename)
        output_bucket = os.getenv("CLEANED_BUCKET", "reviews-bucket-cleaned")
        s3.put_object(Bucket=output_bucket, Key=key, Body=json.dumps(json_data).encode("utf-8"))

    return {"status": "OK"}



