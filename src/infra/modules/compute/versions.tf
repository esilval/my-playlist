# Cómputo de un entorno (feature 004, plan D1, D3, D8): ECR, el clúster de ECS con la API,
# el trabajador y el tiempo real, la tarea de migración y el ALB con su origen HTTPS.
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
