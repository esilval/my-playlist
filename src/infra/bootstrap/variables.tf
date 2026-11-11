variable "region" {
  description = "Región de AWS de los recursos regionales: la única que permite la organización (ADR-0019, D18)."
  type        = string
  default     = "us-east-2"
}

variable "create_github_oidc_provider" {
  description = <<-EOT
    Si el arranque crea el proveedor OIDC de GitHub. La organización de AWS lo prohíbe
    (SCP p-n79p9if6): mientras no haya excepción, lo crea quien la administra, y aquí solo
    se referencia por su ARN, que es fijo (D18).
  EOT
  type        = bool
  default     = false
}

variable "github_repository" {
  description = "Repositorio de GitHub, `dueño/nombre`, cuyos flujos pueden asumir los roles (ADR-0017)."
  type        = string
  default     = "esilval/my-playlist"
}

variable "domain" {
  description = "Dominio del servicio: su zona de Route 53 (plan D1)."
  type        = string
  default     = "200oklabs.com"
}

variable "state_bucket_name" {
  description = "Bucket del estado de Terraform. El nombre es global en S3."
  type        = string
  default     = "myplaylist-200oklabs-terraform-state"
}

variable "deploy_environments" {
  description = "Entornos de GitHub desde los que se puede asumir el rol de despliegue (ADR-0017, D9, D13, D14)."
  type        = list(string)
  default     = ["production", "preproduction"]
}
