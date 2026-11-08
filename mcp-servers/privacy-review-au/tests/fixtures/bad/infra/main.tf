provider "aws" { region = "us-east-1" }
resource "aws_s3_bucket_acl" "records" { bucket = "patient-records" acl = "public-read" }
resource "aws_cognito_user_pool" "pool" { name = "patients" mfa_configuration = "OFF" }
