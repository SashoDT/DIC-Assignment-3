import json
import os
import string
import nltk
from nltk.stem import WordNetLemmatizer
import boto3

# NLTK setup: ensure required resources are available in /tmp (without this, we had trouble with nltk)
nltk.data.path.append("/tmp")
nltk.download("wordnet", download_dir="/tmp")
nltk.download("omw-1.4", download_dir="/tmp")

# Initialize the lemmatizer
lemmatizer = WordNetLemmatizer()

# Load the stopwords from the file at startup
with open(os.path.join(os.path.dirname(__file__), "stopwords.txt"), "r", encoding="utf-8") as f:
    STOPWORDS = set(word.strip().lower() for word in f if word.strip())

def preprocess_text(text):
    """
    This cleans and preprocesses the input by:
    1. Lowercasing and removing punctuation
    2. Tokenizing
    3. Removing stopwords seen in the file and non-ASCII tokens
    4. Lemmatizing the words that are left

    Returns a list of cleaned tokens
    """
    # Lowercase and remove punctuation
    text = text.lower().translate(str.maketrans("", "", string.punctuation))

    # Tokenize by whitespace
    tokens = text.split()

    # Remove stopwords and non-ascii characters and lemmatize the remaining
    processed = [lemmatizer.lemmatize(word) for word in tokens if word not in STOPWORDS and word.isascii()]

    return processed


def handler(event, context):
    """
    This is what is triggered by S3 upload events

    For each object that is uploaded:
    - Reads the JSON line by line
    - Applies the preprocessing function to 'reviewText' and 'summary'
    - Writes the cleaned result to the next S3 bucket
    """

    for record in event["Records"]:
        # Read JSON from S3 (as string body)
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # Initialize the S3 client
        s3 = boto3.client("s3", endpoint_url=os.getenv("AWS_ENDPOINT_URL"))

        # Download the uploaded file from the bucket
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw_data = obj["Body"].read().decode("utf-8")

        # Preprocess only fields "reviewText" and "Summary", line by line 
        processed_lines = []
        for line in raw_data.strip().splitlines():
            if not line.strip():
                continue
            try:
                json_data = json.loads(line)

                # Preprocess the fields if present
                if "reviewText" in json_data:
                    json_data["reviewText"] = preprocess_text(json_data["reviewText"])
                if "summary" in json_data:
                    json_data["summary"] = preprocess_text(json_data["summary"])
                # Store the cleaned line
                processed_lines.append(json.dumps(json_data))
            except json.JSONDecodeError: # Just in case 
                continue  # Skip bad lines
        
        # Save to output bucket (same filename)
        output_bucket = os.getenv("CLEANED_BUCKET", "reviews-bucket-cleaned")
        s3.put_object(Bucket=output_bucket,
                      Key=key, 
                      Body="\n".join(processed_lines).encode("utf-8") # Join all lines back together
                      )
    # Return a response
    return {"status": "OK"}



