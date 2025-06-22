import os
import json
import boto3

BAD_WORDS_FILE_1 = os.path.join(os.path.dirname(__file__), "bad-words.txt")
BAD_WORDS_FILE_2 = os.path.join(os.path.dirname(__file__), "badwords_profanityfilter.txt")


# Set up AWS clients with LocalStack endpoint
endpoint_url = os.environ.get("AWS_ENDPOINT_URL") or ("http://" + os.environ.get("LOCALSTACK_HOSTNAME", "localhost") + ":4566")
s3 = boto3.client("s3", endpoint_url=endpoint_url)
ssm = boto3.client("ssm", endpoint_url=endpoint_url)

# Get the DynamoDB table for ban status
dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url)
table_name = os.environ.get("BAN_TABLE", "ban_table")
table = dynamodb.Table(table_name)

# Get the bucket names from SSM parameters for result output
presentiment_bucket = ssm.get_parameter(Name="/dic/presentiment_bucket")["Parameter"]["Value"]
output_bucket = ssm.get_parameter(Name="/dic/output_bucket")["Parameter"]["Value"]

# Load bad words from file
with open(BAD_WORDS_FILE_1, "r", encoding="utf-8") as f:
    bad_words1 = set(line.strip().lower() for line in f if line.strip())

# Load bad words from profanityfilter package: 
with open(BAD_WORDS_FILE_2, "r", encoding="utf-8") as f:
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
                reviewer_id = review.get('reviewerID', 'unknown')
                for field in ["reviewText", "summary"]: 
                    tokens = review.get(field, [])
                    if isinstance(tokens, list) and contains_profanity(tokens):
                        flagged = True
                        # Logic for updating the DynamoDB table 
                        resp = table.update_item(
                            Key={"reviewerID": reviewer_id},
                            UpdateExpression="ADD profane_count :one SET banned = if_not_exists(banned, :false)",
                            ExpressionAttributeValues={":one": 1,":false": False},
                            ReturnValues="UPDATED_NEW"
                        )
                        # Logic for user banning
                        profane_count = int(resp["Attributes"].get("profane_count", 0))
                        if profane_count > 3 and not resp["Attributes"].get("banned", False):
                            print(f"Banning user {reviewer_id} for excessive profanity.")
                            table.update_item(
                                Key={"reviewerID": reviewer_id},
                                UpdateExpression="SET banned = :true",
                                ExpressionAttributeValues={":true": True}
                            )
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

        #  Fetch banned users from DynamoDB 
        print("Fetching banned users from DynamoDB...")
        banned_users = table.scan(
            FilterExpression="banned = :true",
            ExpressionAttributeValues={":true": True}
        ).get("Items", [])
        
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

        banned_json = "\n".join(json.dumps(user, cls=DecimalEncoder) for user in banned_users).encode("utf-8")
        s3.put_object(
            Bucket=output_bucket,
            Key="banned-users.json",
            Body=banned_json,
            ContentType="application/json"
        )
        print(f"Wrote banned-users.json with {len(banned_users)} users.")

    return {"status": "OK"}

