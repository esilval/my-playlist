# El módulo raíz de un entorno (feature 004, plan D13, ADR-0016, ADR-0019). Lo aplican los
# dos entornos, cada uno con su estado y su archivo de variables:
#
#   terraform init -backend-config=environments/<entorno>.backend.hcl
#   terraform apply -var-file=environments/<entorno>.tfvars
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # El bucket y la clave los da environments/<entorno>.backend.hcl.
  backend "s3" {}
}

# Todo recurso lleva la etiqueta `environment`: con ella, destruir la preproducción
# comprueba que no queda nada (R022).
locals {
  tags = {
    project     = "myplaylist"
    environment = var.environment
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

# Solo para el certificado de CloudFront, que tiene que estar en us-east-1 (D18).
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = local.tags
  }
}

locals {
  production = var.environment == "production"
  name       = "myplaylist-${var.environment}"
  domain     = local.production ? "myplaylist.200oklabs.com" : "pre.myplaylist.200oklabs.com"

  # La configuración no secreta de la aplicación (D6). La preproducción usa el catálogo
  # falso y Mailpit; el cómputo le añade SMTP_HOST y SMTP_PORT (D13).
  app_environment = local.production ? {
    ENV                 = "production"
    EMAIL_BACKEND       = "ses"
    EMAIL_FROM          = module.email[0].sender
    PUBLIC_BASE_URL     = "https://${local.domain}"
    CATALOG_PROVIDER    = "youtube"
    DATA_POLICY_VERSION = var.data_policy_version
    } : {
    ENV              = "preproduction"
    EMAIL_BACKEND    = "smtp"
    PUBLIC_BASE_URL  = "https://${local.domain}"
    CATALOG_PROVIDER = "fake"
  }
}

module "network" {
  source = "./modules/network"

  name               = local.name
  availability_zones = var.availability_zones
  # Solo en preproducción: los puertos de Mailpit entre las tareas (D13).
  mailpit_ports = module.compute.mailpit_ports
}

module "secrets" {
  source = "./modules/secrets"

  name       = "myplaylist/${var.environment}"
  production = local.production
  rotation   = var.secret_rotation
}

# El token de Redis se lee de su secreto sin pasar por el estado, y ElastiCache lo recibe
# por solo escritura (D6). Espera a que el módulo de secretos haya escrito su versión.
ephemeral "aws_secretsmanager_secret_version" "redis_auth_token" {
  secret_id = module.secrets.secret_arns["redis-auth-token"]

  depends_on = [module.secrets]
}

module "data" {
  source = "./modules/data"

  name                     = local.name
  production               = local.production
  private_subnet_ids       = module.network.private_subnet_ids
  data_security_group_id   = module.network.data_security_group_id
  redis_auth_token         = ephemeral.aws_secretsmanager_secret_version.redis_auth_token.secret_string
  redis_auth_token_version = var.redis_auth_token_version
}

module "observability" {
  source = "./modules/observability"

  name                      = local.name
  environment               = var.environment
  domain                    = local.domain
  alert_email               = var.alert_email
  canary_enabled            = var.canary_enabled
  canary_establishment_code = var.canary_establishment_code
  cluster_name              = module.compute.cluster_name
  alb_arn_suffix            = module.compute.alb_arn_suffix
  target_group_arn_suffixes = module.compute.target_group_arn_suffixes
  email_identity_arn        = local.production ? module.email[0].identity_arn : null
}

# Solo producción envía con SES; la preproducción, a Mailpit (D13, D14).
module "email" {
  source = "./modules/email"
  count  = local.production ? 1 : 0

  domain           = local.domain
  zone_id          = var.zone_id
  region           = var.region
  alerts_topic_arn = module.observability.alerts_topic_arn
}

# El cómputo y el borde leen la cabecera de CloudFront de su secreto: después del módulo
# de secretos, para que ya tenga versión y una rotación llegue a los dos en el mismo apply
# (D6).
module "compute" {
  source = "./modules/compute"

  name                    = local.name
  production              = local.production
  region                  = var.region
  domain                  = local.domain
  zone_id                 = var.zone_id
  public_validation_fqdn  = module.edge.public_validation_fqdn
  email_identity_arn      = local.production ? module.email[0].identity_arn : null
  vpc_id                  = module.network.vpc_id
  public_subnet_ids       = module.network.public_subnet_ids
  alb_security_group_id   = module.network.alb_security_group_id
  tasks_security_group_id = module.network.tasks_security_group_id
  secret_arns             = module.secrets.secret_arns
  master_user_secret_arn  = module.data.master_user_secret_arn
  database = {
    host = module.data.database_host
    port = module.data.database_port
    name = module.data.database_name
  }
  redis = {
    host = module.data.redis_host
    port = module.data.redis_port
  }
  log_groups      = module.observability.log_groups
  image_tag       = var.image_tag
  app_environment = local.app_environment

  depends_on = [module.secrets]
}

module "edge" {
  source = "./modules/edge"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name                     = local.name
  production               = local.production
  domain                   = local.domain
  zone_id                  = var.zone_id
  origin_domain            = module.compute.origin_domain
  origin_header_name       = module.compute.origin_header_name
  origin_header_secret_arn = module.secrets.secret_arns["cloudfront-origin-header"]

  depends_on = [module.secrets]
}

# Lo que necesitan los flujos de despliegue, retirada y preproducción (T018 a T020).
output "cluster_name" {
  value = module.compute.cluster_name
}

output "service_names" {
  value = module.compute.service_names
}

output "migration_task_definition" {
  value = module.compute.migration_task_definition
}

output "load_test_task_definition" {
  value = module.compute.load_test_task_definition
}

output "repository_urls" {
  value = module.compute.repository_urls
}

output "public_subnet_ids" {
  description = "Para lanzar la migración y k6 con run-task."
  value       = module.network.public_subnet_ids
}

output "tasks_security_group_id" {
  description = "Para lanzar la migración y k6 con run-task."
  value       = module.network.tasks_security_group_id
}

output "spa_bucket" {
  value = module.edge.spa_bucket
}

output "distribution_id" {
  value = module.edge.distribution_id
}

output "key_value_store_arn" {
  value = module.edge.key_value_store_arn
}

output "canary_name" {
  value = module.observability.canary_name
}
