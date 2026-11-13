# Las variables de un entorno (feature 004, plan D13). Los dos entornos usan este mismo
# módulo raíz y solo difieren en lo que fijan sus `environments/<entorno>.tfvars`.

variable "environment" {
  description = "`production` o `preproduction` (D13)."
  type        = string

  validation {
    condition     = contains(["production", "preproduction"], var.environment)
    error_message = "El entorno es production o preproduction."
  }
}

variable "region" {
  description = "La región de todo lo regional (ADR-0019). El certificado de CloudFront va en us-east-1, con el proveedor con alias."
  type        = string
  default     = "us-east-2"
}

variable "availability_zones" {
  description = "Las dos zonas de la región (Q3, D2)."
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]
}

variable "zone_id" {
  description = "La zona de Route 53 de `200oklabs.com`, del arranque (`terraform output zone_id`)."
  type        = string
}

variable "image_tag" {
  description = "La etiqueta de las primeras definiciones de tarea. Después, cada despliegue registra las suyas (D9)."
  type        = string
}

variable "alert_email" {
  description = <<-EOT
    El correo del responsable de operación, que recibe los avisos y el del presupuesto (D12).
    Es un dato personal: no va en los .tfvars versionados, sino en `TF_VAR_alert_email` o en
    el secreto del entorno de GitHub (T018).
  EOT
  type        = string
  sensitive   = true
}

variable "data_policy_version" {
  description = "DATA_POLICY_VERSION de producción: la versión de la política de tratamiento definitiva. La fija production.tfvars cuando llegue el texto (T026)."
  type        = string
  default     = "0000-borrador"

  # La aplicación no arranca en producción con el borrador (D7): mejor que falle el plan.
  validation {
    condition     = var.environment != "production" || var.data_policy_version != "0000-borrador"
    error_message = "Producción necesita la política de tratamiento definitiva (T026): el borrador solo vale en preproducción."
  }
}

variable "canary_enabled" {
  description = "Si el entorno ya atiende: arranca el canario y los avisos de SG3. Un entorno nuevo va en false hasta el primer despliegue; después lo fija su .tfvars, con el código del establecimiento (T016, T018)."
  type        = bool
  default     = false
}

variable "canary_establishment_code" {
  description = "El código del establecimiento de prueba que recorre el canario. Lo genera la aplicación al crearlo, en el primer despliegue (T018)."
  type        = string
  default     = ""

  validation {
    condition     = !var.canary_enabled || var.canary_establishment_code != ""
    error_message = "Para arrancar el canario hace falta el código del establecimiento de prueba."
  }
}

variable "secret_rotation" {
  description = "La versión de cada secreto generado: subir una rota ese secreto (D6)."
  type        = map(number)
  default     = {}
}

variable "redis_auth_token_version" {
  description = "Se sube a la vez que `secret_rotation[\"redis-auth-token\"]` para rotar el token de Redis (D6)."
  type        = number
  default     = 1
}
