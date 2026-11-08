provider "aws" { region = "ap-southeast-2" }
resource "aws_s3_bucket_public_access_block" "b" { bucket = "assets" block_public_acls = true }
