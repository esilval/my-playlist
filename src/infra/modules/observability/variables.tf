variable "name" {
  description = "Prefijo de los nombres: `myplaylist-<entorno>`. Es también el identificador de RDS del módulo de datos."
  type        = string
}

variable "environment" {
  description = "`production` o `preproduction`: da el espacio de nombres de las métricas, `MyPlaylist/<entorno>` (D11)."
  type        = string

  validation {
    condition     = contains(["production", "preproduction"], var.environment)
    error_message = "El entorno es production o preproduction."
  }
}

variable "domain" {
  description = "El dominio público, que recorre el canario (ADR-0020)."
  type        = string
}

variable "canary_establishment_code" {
  description = "El código de un establecimiento de prueba que existe en el entorno: el tercer paso del canario pide su página pública."
  type        = string
}

variable "alert_email" {
  description = "El correo del responsable de operación: recibe los avisos y el del presupuesto (D12). Confirma la suscripción una vez."
  type        = string
}

variable "cluster_name" {
  description = "El clúster de ECS, del módulo de cómputo."
  type        = string
}

variable "alb_arn_suffix" {
  description = "El sufijo del ARN del ALB, del módulo de cómputo, para sus métricas."
  type        = string
}

variable "target_group_arn_suffixes" {
  description = "El sufijo del ARN de cada grupo de destino (api, realtime), del módulo de cómputo."
  type        = map(string)
}

variable "database_max_connections" {
  description = "max_connections de la instancia de RDS (D4): la alarma salta al 80 %."
  type        = number
  default     = 400
}

variable "email_identity_arn" {
  description = "La identidad de SES, solo en producción: el tema admite sus rebotes y quejas (D14)."
  type        = string
  default     = null

  validation {
    condition     = var.environment != "production" || var.email_identity_arn != null
    error_message = "Producción recibe los rebotes y quejas de SES: hace falta la identidad del módulo de correo."
  }
}

variable "monthly_budget_usd" {
  description = "El coste mensual estimado del plan (US$): el presupuesto avisa si el previsto lo supera en un 20 % (D12). Solo en producción, que vigila toda la cuenta."
  type        = number
  default     = 510
}

variable "canary_runtime_version" {
  description = "La versión fija del entorno de Synthetics (ADR-0020). Hay que subirla cuando AWS la retire."
  type        = string
  default     = "syn-nodejs-puppeteer-18.0"
}

variable "canary_enabled" {
  description = <<-EOT
    Si el entorno ya atiende: el canario corre y las alarmas de disponibilidad (SG3) avisan.
    En un entorno nuevo va en false hasta el primer despliegue, que crea el establecimiento
    de prueba: antes, el canario recibiría 404 y no habría tareas sanas, y SG3 avisaría sin
    motivo (T017, T018).
  EOT
  type        = bool
  default     = true
}
