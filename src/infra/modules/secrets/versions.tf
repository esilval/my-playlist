# Secretos de un entorno (feature 004, plan D6). Los que genera Terraform son efímeros y se
# escriben con atributos de solo escritura: su valor no queda en el estado, que lee el rol
# de plan (D16).
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
  }
}
