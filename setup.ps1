# Stop on error
$ErrorActionPreference = "Stop"

# === CONFIGURATION ===
$inputBucket = "reviews-bucket-input"
$preprocessedBucket = "preprocessed-bucket"
$outputBucket = "reviews-bucket-output"
$lambdaFolder = "lambdas/preprocessing"
$packageFolder = "$lambdaFolder/package"
$lambdaZip = "$lambdaFolder/lambda.zip"

# === CREATE BUCKETS ===
awslocal s3 mb "s3://$inputBucket"
awslocal s3 mb "s3://$outputBucket"

# === SET SSM PARAMETERS (overwrite if needed) ===
awslocal ssm put-parameter --name "/localstack-thumbnail-app/buckets/input" --type String --value "$inputBucket" --overwrite
awslocal ssm put-parameter --name "/localstack-thumbnail-app/buckets/output" --type String --value "$outputBucket" --overwrite

# === PREPARE PACKAGE DIRECTORY ===
if (-Not (Test-Path "$packageFolder\handler.py")) {
    Write-Host "Dependencies not found. Installing..."
    if (-Not (Test-Path $packageFolder)) {
        New-Item -ItemType Directory -Path $packageFolder | Out-Null
    }
} else {
    Write-Host "Dependencies already installed. Skipping installation."
}

# Always copy latest handler + stopwords
Copy-Item "$lambdaFolder\handler.py" $packageFolder -Force
Copy-Item "$lambdaFolder\stopwords.txt" $packageFolder -Force

# === CREATE ZIP FROM PACKAGE ===
Push-Location $packageFolder
Compress-Archive -Path * -DestinationPath ../lambda.zip -Force
Pop-Location

# === CREATE LAMBDA (will fail if it already exists, that's okay) ===
awslocal lambda create-function `
    --function-name "preprocessing" `
    --runtime python3.11 `
    --timeout 10 `
    --zip-file "fileb://$lambdaZip" `
    --handler handler.handler `
    --role "arn:aws:iam::000000000000:role/lambda-role" `
    --environment "Variables={STAGE=local}"

# === ADD PERMISSION (fails if already exists, that's okay too) ===
awslocal lambda add-permission `
    --function-name "preprocessing" `
    --action lambda:InvokeFunction `
    --statement-id s3invoke `
    --principal s3.amazonaws.com `
    --source-arn "arn:aws:s3:::$inputBucket"

# === CONNECT S3 TRIGGER TO LAMBDA ===
$lambdaArn = (awslocal lambda get-function --function-name "preprocessing" | ConvertFrom-Json).Configuration.FunctionArn

$escapedJson = '{\"LambdaFunctionConfigurations\":[{\"LambdaFunctionArn\":\"' + $lambdaArn + '\",\"Events\":[\"s3:ObjectCreated:*\"]}]}'

awslocal s3api put-bucket-notification-configuration `
    --bucket $inputBucket `
    --notification-configuration "$escapedJson"

Write-Host "`n✅ Lambda and trigger setup complete!"

