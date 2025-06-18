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

# Set up AWS clients with LocalStack endpoint
endpoint_url = os.environ.get("AWS_ENDPOINT_URL") or ("http://" + os.environ.get("LOCALSTACK_HOSTNAME", "localhost") + ":4566")
s3 = boto3.client("s3", endpoint_url=endpoint_url)
ssm = boto3.client("ssm", endpoint_url=endpoint_url)

# Get the DynamoDB table for ban status
dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
table_name = os.environ.get("BAN_TABLE", "ban_table")
ban_table = dynamodb.Table(table_name)

# Get the DynamoDB table for sentiment counts
table_name2 = os.environ.get("SENTIMENT_TABLE", "sentiment_table")
sentiment_table = dynamodb.Table(table_name2)

# Get the bucket names from SSM parameters for result output
output_bucket = ssm.get_parameter(Name="/dic/output_bucket")["Parameter"]["Value"]

# For some dumb reason, DynamoDB returns Decimal types for numbers, 
# so we need to convert them to JSON-compatible types because for 
# some dumb reason JSONEncoder does not support those dumb Decimal types.
from decimal import Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert to int if it's a whole number, else float
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

# For counting profane reviews and banned users
def get_total_profane_and_banned():
    profane_total = 0
    ban_total = 0
    response = ban_table.scan()

    for item in response["Items"]:
        profane_count = item.get("profane_count", 0)
        ban = item.get("banned", False)
        if isinstance(profane_count, Decimal):  # DynamoDB uses Decimal
            profane_total += int(profane_count)
        if ban:  # Only count banned users
            ban_total += 1 
        
    return  profane_total, ban_total

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

        # For counting the sentiment of reviews
        sentiment_total = {"positive": 0, "neutral": 0, "negative": 0}

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
                
                # Counting sentiment occurrences
                # sentiment_table.update_item(
                #             Key={"sentiment": sentiment},
                #             UpdateExpression="ADD c :one", # used c since "count" and "counter" are reserved words
                #             ExpressionAttributeValues={":one": 1},
                #             ReturnValues="UPDATED_NEW"
                #         )

                # This is a more efficient way to count sentiments
                sentiment_total[sentiment] += 1

                processed_lines.append(json.dumps(review))
            except json.JSONDecodeError:
                continue  # Skip malformed lines

        s3.put_object(
            Bucket=output_bucket,
            Key=key,
            Body="\n".join(processed_lines).encode("utf-8")
        )

    # Update sentiment counts in DynamoDB (Update per sentiment instead of per review previously)
    for sentiment, count in sentiment_total.items():
        sentiment_table.update_item(
            Key={"sentiment": sentiment},
            UpdateExpression="ADD c :one",  # used c since "count" and "counter" are reserved words
            ExpressionAttributeValues={":one": count},
            ReturnValues="UPDATED_NEW"
        )
    
    # To count everything together 
    profane_total, banned_total = get_total_profane_and_banned()
    sentiment_counts = sentiment_table.scan()
    sentiment_counts = {item["sentiment"]: int(item["c"]) for item in sentiment_counts["Items"]}

    # Convert counts to JSON
    count_json = json.dumps({
        "total_profane_reviews": profane_total,
        "total_banned_users": banned_total,
        "sentiment_counts": sentiment_counts,
        "total_reviews_processed": len(processed_lines)
    }, cls=DecimalEncoder, indent = 4)

    # Save the counts to S3
    s3.put_object(
            Bucket=output_bucket,
            Key="total_counts.json",
            Body=count_json,
            ContentType="application/json"
        )

    return {"status": "OK"}
