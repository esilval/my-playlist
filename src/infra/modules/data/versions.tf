# Datos de un entorno (feature 004, plan D4): PostgreSQL en RDS Multi-AZ con copias de 7
# días, y Redis en ElastiCache con una réplica en la otra zona. Los dos, en las subredes
# privadas y solo al alcance de las tareas (D2).
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
