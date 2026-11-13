# El canario de disponibilidad (ADR-0020): cada minuto, tres pasos contra el dominio
# público. Sus artefactos van a un bucket propio que caduca a los 30 días.
locals {
  # Synthetics admite como mucho 21 caracteres en el nombre.
  canary_name = "myplaylist-${local.production ? "prod" : "pre"}"
}

resource "aws_s3_bucket" "canary" {
  bucket = "${var.name}-canary-${data.aws_caller_identity.current.account_id}"
  # Los artefactos no valen nada fuera de su mes: destruir el entorno los borra.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "canary" {
  bucket                  = aws_s3_bucket.canary.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "canary" {
  bucket = aws_s3_bucket.canary.id

  rule {
    id     = "caducan-a-los-30-dias"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }
  }
}

data "aws_iam_policy_document" "canary_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "canary" {
  name               = "${var.name}-canary"
  assume_role_policy = data.aws_iam_policy_document.canary_assume.json
}

# Lo justo de la política que documenta Synthetics: escribir sus artefactos, sus registros
# y sus métricas, en su propio espacio de nombres.
data "aws_iam_policy_document" "canary" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.canary.arn}/*"]
  }

  statement {
    actions   = ["s3:GetBucketLocation"]
    resources = [aws_s3_bucket.canary.arn]
  }

  statement {
    actions   = ["s3:ListAllMyBuckets"]
    resources = ["*"]
  }

  statement {
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/cwsyn-${local.canary_name}-*"]
  }

  statement {
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["CloudWatchSynthetics"]
    }
  }
}

resource "aws_iam_role_policy" "canary" {
  name   = "canary"
  role   = aws_iam_role.canary.id
  policy = data.aws_iam_policy_document.canary.json
}

# Los entornos de Node de Synthetics buscan el guion en nodejs/node_modules/. La ruta del zip
# lleva el hash del guion: el canario solo se actualiza cuando cambia su `zip_file`.
data "archive_file" "canary" {
  type        = "zip"
  output_path = "${path.module}/.build/canary-${sha1(file("${path.module}/canary/canary.js"))}.zip"

  source {
    content  = file("${path.module}/canary/canary.js")
    filename = "nodejs/node_modules/canary.js"
  }
}

resource "aws_synthetics_canary" "availability" {
  name                 = local.canary_name
  runtime_version      = var.canary_runtime_version
  handler              = "canary.handler"
  zip_file             = data.archive_file.canary.output_path
  execution_role_arn   = aws_iam_role.canary.arn
  artifact_s3_location = "s3://${aws_s3_bucket.canary.bucket}/"
  start_canary         = var.canary_enabled
  # Al destruirse, se lleva su Lambda y su capa, que no llevan la etiqueta `environment`
  # (R022).
  delete_lambda = true

  success_retention_period = 30
  failure_retention_period = 30

  schedule {
    expression = "rate(1 minute)"
  }

  run_config {
    timeout_in_seconds = 50
    environment_variables = {
      CANARY_HOSTNAME    = var.domain
      ESTABLISHMENT_CODE = var.canary_establishment_code
    }
  }

  depends_on = [aws_iam_role_policy.canary]
}
