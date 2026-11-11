# Red de un entorno (feature 004, plan D2): una VPC en dos zonas, sin NAT. El ALB y las
# tareas de ECS van en subredes públicas; RDS y ElastiCache, en privadas sin salida.
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
