import os
import json
import time
import unittest
import boto3
from decimal import Decimal
from botocore.config import Config
import botocore
import botocore.exceptions

import nltk
from nltk.stem import WordNetLemmatizer

# Ensure NLTK resources are available
nltk.data.path.append("/tmp")
try:
    nltk.data.find("corpora/wordnet")
    nltk.data.find("omw-1.4")
except LookupError:
    nltk.download("wordnet", download_dir="/tmp")
    nltk.download("omw-1.4", download_dir="/tmp")

from lambdas.sentiment_analysis.handler import (
    get_total_profane_and_banned,
    classify_sentiment,
    handler as sentiment_handler,
)

# Load stopwords
with open(
    os.path.join(os.path.dirname(__file__), "stopwords.txt"), "r", encoding="utf-8"
) as f:
    STOPWORDS = set(word.strip().lower() for word in f if word.strip())

# Environment for Localstack
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
os.environ["BAN_TABLE"] = "ban_table"
os.environ["SENTIMENT_TABLE"] = "sentiment_table"
os.environ["AWS_ENDPOINT_URL"] = "http://localhost.localstack.cloud:4566"

# Boto3 Clients
s3 = boto3.client("s3", endpoint_url=os.environ["AWS_ENDPOINT_URL"], config=Config(connect_timeout=10, read_timeout=20))
dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ["AWS_ENDPOINT_URL"])
ssm = boto3.client("ssm", endpoint_url=os.environ["AWS_ENDPOINT_URL"])
lambda_client = boto3.client(
    "lambda", endpoint_url="http://localhost.localstack.cloud:4566"
)


class TestSentimentAnalysis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ban_table_name = os.environ["BAN_TABLE"]
        cls.sentiment_table_name = os.environ["SENTIMENT_TABLE"]
        cls.input_bucket = "test-sentiment-input"
        cls.output_bucket = "test-sentiment-output"

        # Create buckets
        for bucket in [cls.input_bucket, cls.output_bucket]:
            try:
                s3.create_bucket(Bucket=bucket)
            except botocore.exceptions.ClientError as e:
                if e.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                    raise

        ssm.put_parameter(
            Name="/dic/output_bucket",
            Value=cls.output_bucket,
            Type="String",
            Overwrite=True,
        )

        # Recreate ban_table
        try:
            table = dynamodb.Table(cls.ban_table_name)
            table.delete()
            table.wait_until_not_exists()
        except:
            pass

        dynamodb.create_table(
            TableName=cls.ban_table_name,
            KeySchema=[{"AttributeName": "reviewerID", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "reviewerID", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        ).wait_until_exists()

        # Recreate sentiment_table
        try:
            table = dynamodb.Table(cls.sentiment_table_name)
            table.delete()
            table.wait_until_not_exists()
        except:
            pass

        dynamodb.create_table(
            TableName=cls.sentiment_table_name,
            KeySchema=[{"AttributeName": "sentiment", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "sentiment", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        ).wait_until_exists()

    def test_classify_sentiment(self):
        """Tests the classification of input text and compound scores with classify_sentiment() with mock data."""
        self.assertEqual(
            classify_sentiment("This is the best product ever", 5), "positive"
        )
        self.assertEqual(classify_sentiment("It is a product", 3), "neutral")
        self.assertEqual(
            classify_sentiment("Terrible and disappointing", 1), "negative"
        )

    def test_get_total_profane_and_banned(self):
        """Tests the counting of profane reviews and banned users."""
        table = dynamodb.Table(self.ban_table_name)
        table.put_item(
            Item={"reviewerID": "user1", "profane_count": Decimal(3), "banned": False}
        )
        table.put_item(
            Item={"reviewerID": "user2", "profane_count": Decimal(5), "banned": True}
        )
        table.put_item(
            Item={"reviewerID": "user3", "profane_count": Decimal(2), "banned": True}
        )

        profane, banned = get_total_profane_and_banned()
        self.assertEqual(profane, 10)
        self.assertEqual(banned, 2)

    def test_handler_sentiment_and_output(self):
        """tests the behaviour of he handler() function, specifically
        - the status output
        - the sentiment
        - the total reviews
        If uses a sample review, puts it into the bucket, triggers the handler and verifies the process, sentiment count and total count output.
        """
        # sample review
        review = {
            "reviewerID": "userx",
            "reviewText": ["the", "product", "is", "awesome"],
            "summary": ["loved", "it"],
            "overall": 5,
        }

        key = "sentiment-review.json"
        s3.put_object(Bucket=self.input_bucket, Key=key, Body=json.dumps(review) + "\n")

        event = {
            "Records": [
                {"s3": {"bucket": {"name": self.input_bucket}, "object": {"key": key}}}
            ]
        }

        response = sentiment_handler(event, None)
        self.assertEqual(response["status"], "OK")

        # check output bucket for processed review
        result = s3.get_object(Bucket=self.output_bucket, Key=key)
        processed = json.loads(result["Body"].read().decode("utf-8").strip())
        self.assertIn("sentiment", processed)
        self.assertEqual(processed["sentiment"], "positive")

        # check counts
        counts_obj = s3.get_object(Bucket=self.output_bucket, Key="total_counts.json")
        counts = json.loads(counts_obj["Body"].read().decode("utf-8"))
        self.assertEqual(counts["total_reviews_processed"], 1)
        self.assertEqual(counts["sentiment_counts"]["positive"], 1)


if __name__ == "__main__":
    unittest.main()
