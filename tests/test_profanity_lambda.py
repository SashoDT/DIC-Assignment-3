import os
import json
import time
import unittest
import boto3
from decimal import Decimal
import botocore
import botocore.exceptions

from lambdas.profanity_check.handler import (
    contains_profanity,
    handler as profanity_handler,
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
os.environ["AWS_ENDPOINT_URL"] = "http://localhost.localstack.cloud:4566"

# Boto3 Clients
s3 = boto3.client("s3", endpoint_url=os.environ["AWS_ENDPOINT_URL"])
dynamodb = boto3.resource("dynamodb", endpoint_url=os.environ["AWS_ENDPOINT_URL"])
ssm = boto3.client("ssm", endpoint_url=os.environ["AWS_ENDPOINT_URL"])

# Sample Data
sample_review = {
    "reviewerID": "TESTUSER1",
    "reviewText": ["this", "product", "is", "total", "crap"],
    "summary": ["absolute", "crap"],
}

clean_review = {
    "reviewerID": "CLEANUSER1",
    "reviewText": ["this", "product", "is", "amazing", "and", "awesome"],
    "summary": ["fantastic"],
}


def wait_for_s3_key(s3_client, bucket, key, timeout=20):
    """Wait for S3 key to appear"""
    for _ in range(timeout * 2):
        try:
            return s3_client.get_object(Bucket=bucket, Key=key)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                time.sleep(0.5)
            else:
                raise
    raise TimeoutError(
        f"S3 key {key} not found in bucket {bucket} after {timeout} seconds"
    )


class TestProfanityHandler(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ban_table = os.environ["BAN_TABLE"]
        cls.input_bucket = "test-input-bucket"
        cls.presentiment_bucket = "test-presentiment-bucket"
        cls.output_bucket = "test-output-bucket"

        # Create buckets
        for bucket in [cls.input_bucket, cls.presentiment_bucket, cls.output_bucket]:
            try:
                s3.create_bucket(Bucket=bucket)
            except botocore.exceptions.ClientError as e:
                if e.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                    raise

        # Delete ban_table if exists, then create it
        try:
            table = dynamodb.Table(cls.ban_table)
            table.delete()
            table.wait_until_not_exists()
        except dynamodb.meta.client.exceptions.ResourceNotFoundException:
            pass

        dynamodb.create_table(
            TableName=cls.ban_table,
            KeySchema=[{"AttributeName": "reviewerID", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "reviewerID", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.Table(cls.ban_table).wait_until_exists()

        ssm.put_parameter(
            Name="/dic/presentiment_bucket",
            Value=cls.presentiment_bucket,
            Type="String",
            Overwrite=True,
        )
        ssm.put_parameter(
            Name="/dic/output_bucket",
            Value=cls.output_bucket,
            Type="String",
            Overwrite=True,
        )

    def test_contains_profanity(self):
        """Test profanity detection logic"""
        self.assertTrue(contains_profanity(sample_review["reviewText"]))
        self.assertTrue(contains_profanity(sample_review["summary"]))
        self.assertFalse(contains_profanity(clean_review["reviewText"]))
        self.assertFalse(contains_profanity(clean_review["summary"]))

    def test_handler_profanity_flag_and_ban_logic(self):
        """Test handler flags profanity and bans after 4 offenses."""
        table = dynamodb.Table(self.ban_table)

        for i in range(4):
            key = f"profane-review-{i}.json"
            content = json.dumps(sample_review)
            s3.put_object(Bucket=self.input_bucket, Key=key, Body=content)

            event = {
                "Records": [
                    {
                        "s3": {
                            "bucket": {"name": self.input_bucket},
                            "object": {"key": key},
                        }
                    }
                ]
            }

            profanity_handler(event, None)

        # Check in DynamoDB
        response = table.get_item(Key={"reviewerID": "TESTUSER1"})
        user = response.get("Item", {})
        print("Ban Table Entry:", user)
        self.assertGreaterEqual(user.get("profane_count", 0), 4)
        self.assertTrue(user.get("banned", False))

    def test_handler_does_not_flag_clean_reviews(self):
        """Checks that clean reviews should not be flagged."""
        key = "clean-review.json"
        content = json.dumps(clean_review)
        s3.put_object(Bucket=self.input_bucket, Key=key, Body=content)

        event = {
            "Records": [
                {"s3": {"bucket": {"name": self.input_bucket}, "object": {"key": key}}}
            ]
        }

        profanity_handler(event, None)

        result = wait_for_s3_key(s3, self.presentiment_bucket, key, timeout=20)
        review_data = json.loads(result["Body"].read().decode("utf-8"))

        print("Clean Review Processed:", review_data)
        self.assertFalse(review_data.get("has_profanity", True))


if __name__ == "__main__":
    unittest.main()
