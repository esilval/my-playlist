# Arranque único de la infraestructura (feature 004, plan D17, ADR-0016). Lo aplica una
# vez, con credenciales de administrador, una persona desde su equipo: crea lo que el
# despliegue necesita para existir. Todo lo demás pasa por los flujos con aprobación.
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = "myplaylist"
      managed_by = "terraform"
      stack      = "bootstrap"
    }
  }
}
