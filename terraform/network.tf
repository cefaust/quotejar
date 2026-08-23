# Security groups and VPC endpoints.
#
# The groups reference each other rather than CIDR blocks: the RDS group
# allows 5432 *from the Lambda group*, not from an address range. That way the
# rule keeps meaning what it says when addresses change, and nothing is
# granted to whatever else happens to share a subnet.
#
# The RDS group has **no standing CIDR ingress at all** -- admin access is
# just-in-time, added and removed around a session. See the README runbook.
#
# Two endpoints, two types, and the difference is worth knowing:
#
#   - Secrets Manager is an **Interface** endpoint: a real ENI with a private
#     IP in the subnet, billed hourly (~$7/month).
#   - DynamoDB is a **Gateway** endpoint: an entry in a route table pointing
#     at an AWS prefix list. No ENI, no address, nothing inbound to attack,
#     and free.
#
# The Lambda has no route to the internet, so both exist because a private
# path is the only path.

resource "aws_security_group" "vpc_endpoint" {
  description = "QuoteJar: HTTPS from Lambda to Secrets Manager VPC endpoint"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress = [{
    cidr_blocks      = []
    description      = "quotejar lambda"
    from_port        = 443
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0c47444c43f3ed25f"]
    self             = false
    to_port          = 443
  }]
  name                   = "quotejar-vpce-sg"
  revoke_rules_on_delete = null
  tags                   = {}
  tags_all               = {}
  vpc_id                 = var.vpc_id
}

resource "aws_security_group" "rds" {
  description = "QuoteJar RDS: postgres from admin IP and App Runner only"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress = [{
    cidr_blocks      = []
    description      = "quotejar lambda"
    from_port        = 5432
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0c47444c43f3ed25f"]
    self             = false
    to_port          = 5432
  }]
  name                   = "quotejar-rds-sg"
  revoke_rules_on_delete = null
  tags                   = {}
  tags_all               = {}
  vpc_id                 = var.vpc_id
}

resource "aws_security_group" "lambda" {
  description = "QuoteJar Lambda: egress to RDS and Secrets Manager endpoint"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress                = []
  name                   = "quotejar-lambda-sg"
  revoke_rules_on_delete = null
  tags                   = {}
  tags_all               = {}
  vpc_id                 = var.vpc_id
}

resource "aws_vpc_endpoint" "dynamodb" {
  auto_accept     = null
  ip_address_type = "ipv4"
  policy = jsonencode({
    Statement = [{
      Action    = "*"
      Effect    = "Allow"
      Principal = "*"
      Resource  = "*"
    }]
    Version = "2008-10-17"
  })
  private_dns_enabled        = false
  resource_configuration_arn = null
  route_table_ids            = [var.route_table_id]
  security_group_ids         = []
  service_name               = "com.amazonaws.us-east-1.dynamodb"
  service_network_arn        = null
  service_region             = data.aws_region.current.region
  subnet_ids                 = []
  tags                       = {}
  tags_all                   = {}
  vpc_endpoint_type          = "Gateway"
  vpc_id                     = var.vpc_id
  dns_options {
    dns_record_ip_type                             = "service-defined"
    private_dns_only_for_inbound_resolver_endpoint = false
  }
}

resource "aws_vpc_endpoint" "secretsmanager" {
  auto_accept     = null
  ip_address_type = "ipv4"
  policy = jsonencode({
    Statement = [{
      Action    = "*"
      Effect    = "Allow"
      Principal = "*"
      Resource  = "*"
    }]
  })
  private_dns_enabled        = true
  resource_configuration_arn = null
  route_table_ids            = []
  security_group_ids         = ["sg-04efb90f045da68c7"]
  service_name               = "com.amazonaws.us-east-1.secretsmanager"
  service_network_arn        = null
  service_region             = data.aws_region.current.region
  subnet_ids                 = ["subnet-05ea50db0fd8c9ab0"]
  tags                       = {}
  tags_all                   = {}
  vpc_endpoint_type          = "Interface"
  vpc_id                     = var.vpc_id
  dns_options {
    dns_record_ip_type                             = "ipv4"
    private_dns_only_for_inbound_resolver_endpoint = false
  }
  subnet_configuration {
    ipv4      = "172.31.92.57"
    ipv6      = null
    subnet_id = "subnet-05ea50db0fd8c9ab0"
  }
}
