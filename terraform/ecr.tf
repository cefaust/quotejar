# Container registry for the Lambda image.
#
# force_delete is false, so `terraform destroy` refuses while images remain
# rather than silently deleting the artefact every past deploy points at.

resource "aws_ecr_repository" "app" {
  force_delete         = null
  image_tag_mutability = "MUTABLE"
  name                 = "quotejar"
  tags                 = {}
  tags_all             = {}
  encryption_configuration {
    encryption_type = "AES256"
  }
  image_scanning_configuration {
    scan_on_push = true
  }
}
