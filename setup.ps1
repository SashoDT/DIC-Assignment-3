# Stop on error
$ErrorActionPreference = "Stop"

# === CONFIGURATION ===
$inputBucket = "reviews-bucket-input"
$cleanedBucket = "reviews-bucket-cleaned"
$presentimentBucket = "reviews-bucket-presentiment"
$outputBucket = "reviews-bucket-output"

$preprocessName = "preprocessing"
$profanityName = "profanity-check"
$sentimentName = "sentiment-analysis"

$preprocessFolder = "lambdas/preprocessing"
$profanityFolder = "lambdas/profanity-check"
$sentimentFolder = "lambdas/sentiment-analysis"

$preprocessPackage = "$preprocessFolder/package"
$profanityPackage = "$profanityFolder/package"
$sentimentPackage = "$sentimentFolder/package"

$preprocessZip = "$preprocessFolder/lambda.zip"
$profanityZip = "$profanityFolder/lambda.zip"
$sentimentZip = "$sentimentFolder/lambda.zip"

# === CREATE BUCKETS ===
awslocal s3 mb "s3://$inputBucket"
awslocal s3 mb "s3://$cleanedBucket"
awslocal s3 mb "s3://$presentimentBucket"
awslocal s3 mb "s3://$outputBucket"

# === SET SSM PARAMETERS ===
awslocal ssm put-parameter --name "/dic/input_bucket" --type String --value "$inputBucket" --overwrite
awslocal ssm put-parameter --name "/dic/cleaned_bucket" --type String --value "$cleanedBucket" --overwrite
awslocal ssm put-parameter --name "/dic/presentiment_bucket" --type String --value "$presentimentBucket" --overwrite
awslocal ssm put-parameter --name "/dic/output_bucket" --type String --value "$outputBucket" --overwrite

# === PACKAGE & DEPLOY: PREPROCESSING ===
if (-Not (Test-Path "$preprocessPackage\handler.py")) {
    Write-Host "Installing preprocessing dependencies..."
    if (-Not (Test-Path $preprocessPackage)) {
        New-Item -ItemType Directory -Path $preprocessPackage | Out-Null
    }
    pip install -r "$preprocessFolder/requirements.txt" -t $preprocessPackage `
        --platform manylinux2014_x86_64 `
        --only-binary=:all: `
        --upgrade `
        --no-deps
}

Copy-Item "$preprocessFolder\handler.py" $preprocessPackage -Force
Copy-Item "$preprocessFolder\stopwords.txt" $preprocessPackage -Force
Push-Location $preprocessPackage
Compress-Archive -Path * -DestinationPath ../lambda.zip -Force
Pop-Location

awslocal lambda create-function `
    --function-name $preprocessName `
    --runtime python3.11 `
    --timeout 10 `
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

# Add trigger for the preprocessing
$preprocessArn = (awslocal lambda get-function --function-name $preprocessName | ConvertFrom-Json).Configuration.FunctionArn
$preprocessConfig = '{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"' + $preprocessArn + '\",\"Events\":[\"s3:ObjectCreated:*\"]}]}'

awslocal s3api put-bucket-notification-configuration `
    --bucket $inputBucket `
    --notification-configuration "$preprocessConfig"

# === PACKAGE & DEPLOY: PROFANITY-CHECK ===
if (-Not (Test-Path "$profanityPackage\handler.py")) {
    Write-Host "Installing profanity-check dependencies..."
    if (-Not (Test-Path $profanityPackage)) {
        New-Item -ItemType Directory -Path $profanityPackage | Out-Null
    }
}
Copy-Item "$profanityFolder\handler.py" $profanityPackage -Force
Copy-Item "$profanityFolder\bad-words.txt" $profanityPackage -Force
Push-Location $profanityPackage
Compress-Archive -Path * -DestinationPath ../lambda.zip -Force
Pop-Location

awslocal lambda create-function `
    --function-name $profanityName `
    --runtime python3.11 `
    --timeout 10 `
    --zip-file "fileb://$profanityZip" `
    --handler handler.handler `
    --role "arn:aws:iam::000000000000:role/lambda-role" `
    --environment "Variables={STAGE=local,PRESENTIMENT_BUCKET=$presentimentBucket}"

# Allow S3 to invoke
awslocal lambda add-permission `
    --function-name $profanityName `
    --action lambda:InvokeFunction `
    --statement-id s3invoke2 `
    --principal s3.amazonaws.com `
    --source-arn "arn:aws:s3:::$cleanedBucket"

# Add trigger for the profanity check
$profanityArn = (awslocal lambda get-function --function-name $profanityName | ConvertFrom-Json).Configuration.FunctionArn
$profanityConfig = '{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"' + $profanityArn + '\",\"Events\":[\"s3:ObjectCreated:*\"]}]}'

awslocal s3api put-bucket-notification-configuration `
    --bucket $cleanedBucket `
    --notification-configuration "$profanityConfig"

# === PACKAGE & DEPLOY: SENTIMENT ANALYSIS ===
if (-Not (Test-Path "$sentimentPackage\handler.py")) {
    Write-Host "Installing sentiment-analysis dependencies..."
    if (-Not (Test-Path $sentimentPackage)) {
        New-Item -ItemType Directory -Path $sentimentPackage | Out-Null
    }
    pip install -r "$sentimentFolder/requirements.txt" -t $sentimentPackage --platform manylinux2014_x86_64 --only-binary=:all: --upgrade --no-deps

}
Copy-Item "$sentimentFolder\handler.py" $sentimentPackage -Force
Push-Location $sentimentPackage
Compress-Archive -Path * -DestinationPath ../lambda.zip -Force
Pop-Location

awslocal lambda create-function `
    --function-name $sentimentName `
    --runtime python3.11 `
    --timeout 10 `
    --zip-file "fileb://$sentimentZip" `
    --handler handler.handler `
    --role "arn:aws:iam::000000000000:role/lambda-role" `
    --environment "Variables={STAGE=local,OUTPUT_BUCKET=$outputBucket}"

awslocal lambda add-permission `
    --function-name $sentimentName `
    --action lambda:InvokeFunction `
    --statement-id s3invoke3 `
    --principal s3.amazonaws.com `
    --source-arn "arn:aws:s3:::$presentimentBucket"

$sentimentArn = (awslocal lambda get-function --function-name $sentimentName | ConvertFrom-Json).Configuration.FunctionArn
$sentimentConfig = '{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"' + $sentimentArn + '\",\"Events\":[\"s3:ObjectCreated:*\"]}]}'

awslocal s3api put-bucket-notification-configuration `
    --bucket $presentimentBucket `
    --notification-configuration "$sentimentConfig"

Write-Host "`nAll Lambdas and triggers are configured!"


