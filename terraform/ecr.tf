# Container registry for the Lambda image.
#
# force_delete is unset, which defaults to false, so `terraform destroy`
# refuses while images remain rather than silently deleting the artefact every
# past deploy points at. Left unset rather than written as `false` so the
# config keeps matching the live resource exactly -- the point of the clean
# plan is that nothing here is aspirational.

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
