import os
import json
import pytest
import boto3

import unittest
import nltk
from nltk.stem import WordNetLemmatizer
from lambdas.preprocessing import handler


# Ensure NLTK resources are available
nltk.data.path.append("/tmp")
try:
    nltk.data.find("corpora/wordnet")
    nltk.data.find("omw-1.4")
except LookupError:
    nltk.download("wordnet", download_dir="/tmp")
    nltk.download("omw-1.4", download_dir="/tmp")

with open(os.path.join(os.path.dirname(__file__), "stopwords.txt"), "r", encoding="utf-8") as f:
    STOPWORDS = set(word.strip().lower() for word in f if word.strip())


# Setup environment for Localstack
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"

lambda_client = boto3.client(
    "lambda", endpoint_url="http://localhost.localstack.cloud:4566"
)

sample_data = (
    {
        "reviewerID": "A2VNYWOPJ13AFP",
        "asin": "0981850006",
        "reviewerName": 'Amazon Customer "carringt0n"',
        "helpful": [6, 7],
        "reviewText": "This was a gift for my other husband.  He's making us things from it all the time and we love the food.  Directions are simple, easy to read and interpret, and fun to make.  We all love different kinds of cuisine and Raichlen provides recipes from everywhere along the barbecue trail as he calls it. Get it and just open a page.  Have at it.  You'll love the food and it has provided us with an insight into the culture that produced it. It's all about broadening horizons.  Yum!!",
        "overall": 5.0,
        "summary": "Delish",
        "unixReviewTime": 1259798400,
        "reviewTime": "12 3, 2009",
        "category": "Patio_Lawn_and_Garde",
        "expected_review_tokens": ['gift', 'husband', 'he', 'making', 'thing', 'time', 'love', 'food', 'direction', 'simple', 'easy', 'interpret', 'make', 'love', 'kind', 'cuisine', 'raichlen', 'recipe', 'barbecue', 'trail', 'call', 'open', 'page', 'youll', 'love', 'food', 'provided', 'insight', 'culture', 'produced', 'broadening', 'horizon', 'yum'],
        "expected_summary_tokens": ["delish"]
    },
{
    "reviewerID": "A123XYZ",
    "asin": "B00TEST123",
    "reviewerName": "John Doe",
    "helpful": [2, 3],
    "reviewText": "This product is absolutely the worst damn thing I've ever bought. It was a total piece of crap — slow, ugly, and stupid. What a freaking mess.",
    "summary": "Total crap!",
    "overall": 1.0,
    "unixReviewTime": 1700000000,
    "reviewTime": "10 25, 2023",
    "category": "Electronics",
    "expected_review_tokens": ['absolutely', 'worst', 'damn', 'thing', 'ive', 'bought', 'total', 'piece', 'crap', 'slow', 'ugly', 'stupid', 'freaking', 'mess'],
    "expected_summary_tokens": ['total', 'crap']
})


@pytest.fixture(autouse=True)
def wait_for_lambda_ready():
    lambda_client.get_waiter("function_active").wait(FunctionName="preprocessing")

class TestPreprocessText(unittest.TestCase):

    def test_review_tokenization(self):
        """ Tests the correct preprocessing in the text."""
        for review in sample_data:
            processed = handler.preprocess_text(review["reviewText"])
            self.assertEqual(processed, review["expected_review_tokens"],
                                  msg=f"Mismatch in reviewText from {review['reviewerID']} tokens\nProcessed: {processed}\nExpected: {review['expected_review_tokens']}")

    def test_summary_tokenization(self):
        """ Tests the correct preprocessing in the summary."""
        for review in sample_data:
            processed_summary = handler.preprocess_text(review["summary"])
            self.assertEqual(processed_summary, review["expected_summary_tokens"],
                                  msg=f"Mismatch in summary from {review['reviewerID']} tokens\nProcessed: {processed_summary}\nExpected: {review['expected_summary_tokens']}")

if __name__ == "__main__":
    unittest.main()