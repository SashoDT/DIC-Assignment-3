# Stop execution if a command fails
$ErrorActionPreference = "Stop"

# === CONFIGURATION ===
# S3 bucket names
$inputBucket = "reviews-bucket-input"
$cleanedBucket = "reviews-bucket-cleaned"
$presentimentBucket = "reviews-bucket-presentiment"
$outputBucket = "reviews-bucket-output"

# DynamoDB table names
$banTable = "ban-table"
$sentimentTable = "sentiment-table" 

# Lambda function names
$preprocessName = "preprocessing"
$profanityName = "profanity_check"
$sentimentName = "sentiment_analysis"

# Paths for each Lambda source code
$preprocessFolder = "lambdas/preprocessing"
$profanityFolder = "lambdas/profanity_check"
$sentimentFolder = "lambdas/sentiment_analysis"

# Paths where the dependancies are installed
$preprocessPackage = "$preprocessFolder/package"
$profanityPackage = "$profanityFolder/package"
$sentimentPackage = "$sentimentFolder/package"

# Where to zip the final packages
$preprocessZip = "$preprocessFolder/lambda.zip"
$profanityZip = "$profanityFolder/lambda.zip"
$sentimentZip = "$sentimentFolder/lambda.zip"

# === CREATE S3 BUCKETS ===
awslocal s3 mb "s3://$inputBucket"
awslocal s3 mb "s3://$cleanedBucket"
awslocal s3 mb "s3://$presentimentBucket"
awslocal s3 mb "s3://$outputBucket"

# === CREATE DYNAMODB TABLE FOR BAN STATUS ===
awslocal dynamodb create-table `
    --table-name $banTable `
    --key-schema AttributeName=reviewerID,KeyType=HASH `
    --attribute-definitions AttributeName=reviewerID,AttributeType=S `
    --billing-mode PAY_PER_REQUEST 

# === CREATE DYNAMODB TABLE FOR SENTIMENT COUNTING ===
awslocal dynamodb create-table `
    --table-name $sentimentTable `
    --key-schema AttributeName=sentiment,KeyType=HASH `
    --attribute-definitions AttributeName=sentiment,AttributeType=S `
    --billing-mode PAY_PER_REQUEST 

# === SET SSM PARAMETERS ===
# This allows lambdas to get bucket and table names from the SSM
awslocal ssm put-parameter --name "/dic/input_bucket" --type String --value "$inputBucket" --overwrite
awslocal ssm put-parameter --name "/dic/cleaned_bucket" --type String --value "$cleanedBucket" --overwrite
awslocal ssm put-parameter --name "/dic/presentiment_bucket" --type String --value "$presentimentBucket" --overwrite
awslocal ssm put-parameter --name "/dic/output_bucket" --type String --value "$outputBucket" --overwrite
awslocal ssm put-parameter --name "/dic/ban_table" --type String --value "$banTable" --overwrite
awslocal ssm put-parameter --name "/dic/sentiment_table" --type String --value "$sentimentTable" --overwrite

# === PACKAGE & DEPLOY: PREPROCESSING ===

# This checks whether the preprocessing lambda dependancies have been installed
if (-Not (Test-Path "$preprocessPackage\handler.py")) {
    Write-Host "Installing preprocessing dependencies..."
    # Create the "package" directory if it doesn't exist
    if (-Not (Test-Path $preprocessPackage)) {
        New-Item -ItemType Directory -Path $preprocessPackage | Out-Null
    }
    # Install the necessary python dependancies from the file
    pip install -r "$preprocessFolder/requirements.txt" -t $preprocessPackage `
        --platform manylinux2014_x86_64 `
        --only-binary=:all: `
        --upgrade `
        --no-deps
}

# Copy the two files into the package
Copy-Item "$preprocessFolder\handler.py" $preprocessPackage -Force
Copy-Item "$preprocessFolder\stopwords.txt" $preprocessPackage -Force

# Create a .zip deployment package
Push-Location $preprocessPackage
Compress-Archive -Path * -DestinationPath ../lambda.zip -Force
Pop-Location

# # Create the preprocessing function
awslocal lambda create-function `
    --function-name $preprocessName `
    --runtime python3.11 `
    --timeout 120 `
    --zip-file "fileb://$preprocessZip" `
    --handler handler.handler `
    --role "arn:aws:iam::000000000000:role/lambda-role" `
    --environment "Variables={STAGE=local,CLEANED_BUCKET=$cleanedBucket}"

# Allow S3 to invoke
awslocal lambda add-permission `
    --function-name $preprocessName `
    --action lambda:InvokeFunction `
    --statement-id s3invoke `
    --principal s3.amazonaws.com `
    --source-arn "arn:aws:s3:::$inputBucket"

# Add the S3 trigger for the preprocessing
$preprocessArn = (awslocal lambda get-function --function-name $preprocessName | ConvertFrom-Json).Configuration.FunctionArn
$preprocessConfig = '{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"' + $preprocessArn + '\",\"Events\":[\"s3:ObjectCreated:*\"]}]}'

awslocal s3api put-bucket-notification-configuration `
    --bucket $inputBucket `
    --notification-configuration "$preprocessConfig"

# === PACKAGE & DEPLOY: PROFANITY-CHECK ===
# As above, checks dependancies, but for the profanity check
if (-Not (Test-Path "$profanityPackage\handler.py")) {
    Write-Host "Installing profanity_check dependencies..."
    if (-Not (Test-Path $profanityPackage)) {
        New-Item -ItemType Directory -Path $profanityPackage | Out-Null
    }
    pip install -r "$profanityFolder/requirements.txt" -t $profanityPackage --upgrade 
}

# Copy the files into the package
Copy-Item "$profanityFolder\handler.py" $profanityPackage -Force
Copy-Item "$profanityFolder\bad-words.txt" $profanityPackage -Force
Copy-Item "$profanityFolder\badwords_profanityfilter.txt" $profanityPackage -Force

# Zip and package
Push-Location $profanityPackage
Compress-Archive -Path * -DestinationPath ../lambda.zip -Force
Pop-Location

# Create the profanity check lambda function
awslocal lambda create-function `
    --function-name $profanityName `
    --runtime python3.11 `
    --memory-size 1024 `
    --timeout 180 `
    --zip-file "fileb://$profanityZip" `
    --handler handler.handler `
    --role "arn:aws:iam::000000000000:role/lambda-role" `
    --environment "Variables={STAGE=local,PRESENTIMENT_BUCKET=$presentimentBucket,BAN_TABLE=$banTable,OUTPUT_BUCKET=$outputBucket}"

# Allow S3 to invoke
awslocal lambda add-permission `
    --function-name $profanityName `
    --action lambda:InvokeFunction `
    --statement-id s3invoke2 `
    --principal s3.amazonaws.com `
    --source-arn "arn:aws:s3:::$cleanedBucket"

# Add S3 trigger for the profanity check
$profanityArn = (awslocal lambda get-function --function-name $profanityName | ConvertFrom-Json).Configuration.FunctionArn
$profanityConfig = '{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"' + $profanityArn + '\",\"Events\":[\"s3:ObjectCreated:*\"]}]}'

awslocal s3api put-bucket-notification-configuration `
    --bucket $cleanedBucket `
    --notification-configuration "$profanityConfig"

# === PACKAGE & DEPLOY: SENTIMENT ANALYSIS ===

# Same thing as with the previous two functions, but for sentiment analysis
if (-Not (Test-Path "$sentimentPackage\handler.py")) {
    Write-Host "Installing sentiment_analysis dependencies..."
    if (-Not (Test-Path $sentimentPackage)) {
        New-Item -ItemType Directory -Path $sentimentPackage | Out-Null
    }
    pip install -r "$sentimentFolder/requirements.txt" -t $sentimentPackage --platform manylinux2014_x86_64 --only-binary=:all: --upgrade --no-deps

}
Copy-Item "$sentimentFolder\handler.py" $sentimentPackage -Force
Push-Location $sentimentPackage
Compress-Archive -Path * -DestinationPath ../lambda.zip -Force
Pop-Location

# Create the Lambda function for sentiment analysis
awslocal lambda create-function `
    --function-name $sentimentName `
    --runtime python3.11 `
    --timeout 240 `
    --memory-size 1024 `
    --zip-file "fileb://$sentimentZip" `
    --handler handler.handler `
    --role "arn:aws:iam::000000000000:role/lambda-role" `
    --environment "Variables={STAGE=local,OUTPUT_BUCKET=$outputBucket,SENTIMENT_TABLE=$sentimentTable,BAN_TABLE=$banTable}"

# Allow S3 to onvoke
awslocal lambda add-permission `
    --function-name $sentimentName `
    --action lambda:InvokeFunction `
    --statement-id s3invoke3 `
    --principal s3.amazonaws.com `
    --source-arn "arn:aws:s3:::$presentimentBucket"

# And finally set up the sentiment analysis trigger
$sentimentArn = (awslocal lambda get-function --function-name $sentimentName | ConvertFrom-Json).Configuration.FunctionArn
$sentimentConfig = '{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"' + $sentimentArn + '\",\"Events\":[\"s3:ObjectCreated:*\"]}]}'

awslocal s3api put-bucket-notification-configuration `
    --bucket $presentimentBucket `
    --notification-configuration "$sentimentConfig"

# === Create Output Folder ===
if (-Not (Test-Path out)) {
        New-Item -ItemType Directory -Path out | Out-Null
    }

# If this prints, then everything went smoothly
Write-Host "`nAll Lambdas and triggers are configured!"


