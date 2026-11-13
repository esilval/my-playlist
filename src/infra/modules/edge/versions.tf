# El borde de un entorno (feature 004, plan D1, D10, D11): CloudFront delante de todo, con
# su certificado en us-east-1, el bucket de la SPA, la función `edge` y su almacén de claves
# del mantenimiento.
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
      # CloudFront solo admite certificados de us-east-1 (ADR-0019, D18).
      configuration_aliases = [aws.us_east_1]
    }
  }
}
