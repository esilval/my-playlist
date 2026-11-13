# El correo de producción (feature 004, plan D14, ADR-0019): SES en us-east-2, con el
# dominio verificado por DKIM, un MAIL FROM propio con SPF, DMARC y los rebotes y quejas
# en el tema de avisos. La preproducción no lo usa: envía a Mailpit (D13).
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
