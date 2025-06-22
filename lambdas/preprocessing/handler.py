import json
import os
import string
import nltk
from nltk.stem import WordNetLemmatizer

nltk.data.path.append("/tmp")
nltk.download("wordnet", download_dir="/tmp")
nltk.download("omw-1.4", download_dir="/tmp")

lemmatizer = WordNetLemmatizer()

# Load stopwords from file once at startup
with open(os.path.join(os.path.dirname(__file__), "stopwords.txt"), "r", encoding="utf-8") as f:
    STOPWORDS = set(word.strip().lower() for word in f if word.strip())

def preprocess_text(text):
    # Lowercase and remove punctuation
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    if not text.isascii(): print("Non ASCII character detected")
    # Tokenize
    tokens = text.split()
    # Remove stopwords and lemmatize
    processed = [lemmatizer.lemmatize(word) for word in tokens if word not in STOPWORDS and word.isascii()]
    return processed


def handler(event, context):
    for record in event["Records"]:
        # Read JSON from S3 (as string body)
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        import boto3
        s3 = boto3.client("s3", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))

        obj = s3.get_object(Bucket=bucket, Key=key)
        raw_data = obj["Body"].read().decode("utf-8")

        # Preprocess only fields "reviewText" and "Summary", line by line 
        processed_lines = []
        for line in raw_data.strip().splitlines():
            if not line.strip():
                continue
            try:
                json_data = json.loads(line)
                if "reviewText" in json_data:
                    json_data["reviewText"] = preprocess_text(json_data["reviewText"])
                if "summary" in json_data:
                    json_data["summary"] = preprocess_text(json_data["summary"])
                processed_lines.append(json.dumps(json_data))
            except json.JSONDecodeError: # Just in case 
                continue  # Skip bad lines
        
        # Save to output bucket (same filename)
        output_bucket = os.getenv("CLEANED_BUCKET", "reviews-bucket-cleaned")
        s3.put_object(Bucket=output_bucket, 
                      Key=key, 
                      Body="\n".join(processed_lines).encode("utf-8") # Join all lines back together
                      )

    return {"status": "OK"}



