# La observabilidad de un entorno (feature 004, plan D11, D12, ADR-0020): todo en
# us-east-2. Los grupos de registros de 30 días, el tema de avisos, una alarma por umbral,
# el canario de disponibilidad, Contributor Insights, el panel y el presupuesto.
terraform {
  required_version = "~> 1.17"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    # Empaqueta el guion del canario en el zip que pide Synthetics.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}
