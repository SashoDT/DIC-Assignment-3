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

def classify_sentiment(text, rating):
    """Returns 'positive', 'neutral', or 'negative' based on compound score."""
    score = analyzer.polarity_scores(text)["compound"]
    score += (rating-3)/2
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
        raw_data = obj["Body"].read().decode("utf-8")

        processed_lines = []

        # Use the *original text* for sentiment scoring
        for line in raw_data.strip().splitlines():
            if not line.strip():
                continue
            try:
                review = json.loads(line)

                # Join tokenized fields to get the original text
                review_text = " ".join(review.get("reviewText", []))
                summary_text = " ".join(review.get("summary", []))
                overall_rating = review.get("overall", 3.0) # if no rating, then 3
                full_text = f"{summary_text}. {review_text}".strip()

                sentiment = classify_sentiment(full_text, overall_rating)
                review["sentiment"] = sentiment

                processed_lines.append(json.dumps(review))
            except json.JSONDecodeError:
                continue  # Skip malformed lines

        s3.put_object(
            Bucket=output_bucket,
            Key=key,
            Body="\n".join(processed_lines).encode("utf-8")
        )

    return {"status": "OK"}
