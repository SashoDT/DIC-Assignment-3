import os
import json
import boto3
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Download VADER lexicon to a Lambda-writable location
nltk.data.path.append("/tmp")
nltk.download("vader_lexicon", download_dir="/tmp")

# Set NLTK to look in the Lambda-writable directory
os.environ["NLTK_DATA"] = "/tmp"

# Instantiate analyzer
analyzer = SentimentIntensityAnalyzer()

# Set up S3 and output destination
endpoint_url = os.environ.get("AWS_ENDPOINT_URL") or ("http://" + os.environ.get("LOCALSTACK_HOSTNAME", "localhost") + ":4566")
s3 = boto3.client("s3", endpoint_url=endpoint_url)
ssm = boto3.client("ssm", endpoint_url=endpoint_url)

output_bucket = ssm.get_parameter(Name="/dic/output_bucket")["Parameter"]["Value"]

def classify_sentiment(text):
    """Returns 'positive', 'neutral', or 'negative' based on compound score."""
    score = analyzer.polarity_scores(text)["compound"]
    if score >= 0.05:
        return "positive"
    elif score <= -0.05:
        return "negative"
    else:
        return "neutral"

def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        obj = s3.get_object(Bucket=bucket, Key=key)
        review = json.loads(obj["Body"].read().decode("utf-8"))

        # Use the *original text* for sentiment scoring
        review_text = " ".join(review.get("reviewText", []))  # It's tokenized, so join
        summary_text = " ".join(review.get("summary", []))

        full_text = f"{summary_text}. {review_text}".strip()

        sentiment = classify_sentiment(full_text)
        review["sentiment"] = sentiment

        s3.put_object(
            Bucket=output_bucket,
            Key=key,
            Body=json.dumps(review).encode("utf-8")
        )

    return {"status": "OK"}
