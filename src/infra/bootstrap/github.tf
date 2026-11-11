# Acceso de GitHub Actions a AWS con OIDC (ADR-0017): cada ejecución recibe credenciales
# temporales, sin claves guardadas en GitHub.
data "aws_caller_identity" "current" {}

locals {
  oidc_host = "token.actions.githubusercontent.com"
  # El del proveedor que crea este arranque o, si no puede, el que crea quien administra la
  # organización: su ARN solo depende de la cuenta (D18).
  github_oidc_provider_arn = (
    var.create_github_oidc_provider
    ? aws_iam_openid_connect_provider.github[0].arn
    : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_host}"
  )

  # El rol de despliegue solo lo asume un trabajo que corre en un entorno protegido de
  # este repositorio: esos entornos exigen la aprobación de un revisor y solo admiten
  # etiquetas v* (R002, D9, D17).
  deploy_subjects = [
    for environment in var.deploy_environments :
    "repo:${var.github_repository}:environment:${environment}"
  ]
  # El rol de plan lo asumen los PR de este repositorio, para comentar el plan (D16).
  plan_subjects = ["repo:${var.github_repository}:pull_request"]

  deploy_trust = {
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_host}:aud" = "sts.amazonaws.com"
          "${local.oidc_host}:sub" = local.deploy_subjects
        }
      }
    }]
  }

  plan_trust = {
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_host}:aud" = "sts.amazonaws.com"
          "${local.oidc_host}:sub" = local.plan_subjects
        }
      }
    }]
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 1 : 0

  url            = "https://${local.oidc_host}"
  client_id_list = ["sts.amazonaws.com"]
}

# Despliegue: crea y cambia toda la infraestructura, así que sus permisos son amplios
# (ADR-0017, consecuencias). Lo que lo acota es quién puede asumirlo.
resource "aws_iam_role" "deploy" {
  name               = "myplaylist-github-deploy"
  description        = "Despliegue desde los entornos protegidos de GitHub (ADR-0017)"
  assume_role_policy = jsonencode(local.deploy_trust)
  # La prueba de carga en la preproducción (D13) dura unas 3 horas y termina con un
  # `terraform destroy`: con una sesión más corta, las credenciales caducarían antes.
  max_session_duration = 14400
}

resource "aws_iam_role_policy_attachment" "deploy_admin" {
  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# Plan: solo lectura de la cuenta, más lo justo del estado (leerlo y tomar el bloqueo).
resource "aws_iam_role" "plan" {
  name                 = "myplaylist-github-plan"
  description          = "terraform plan en los PR, de solo lectura (D16)"
  assume_role_policy   = jsonencode(local.plan_trust)
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read_only" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "plan_state" {
  name = "terraform-state"
  role = aws_iam_role.plan.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "LeerElEstado"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetObject"]
        Resource = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      },
      {
        # El bloqueo nativo de S3 escribe y borra un archivo .tflock junto al estado.
        Sid      = "BloqueoDelEstado"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.state.arn}/*.tflock"
      },
    ]
  })
}
