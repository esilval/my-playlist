variable "name" {
  description = "Prefijo de los secretos: `myplaylist/<entorno>`."
  type        = string
}

variable "production" {
  description = "Producción guarda 30 días un secreto borrado; la preproducción lo borra al momento, para destruirse sin dejar nada (R022)."
  type        = bool
}

variable "rotation" {
  description = <<-EOT
    Versión de cada secreto generado. Para rotar uno, se sube su número: Terraform genera un
    valor nuevo y lo escribe (D6). Los que no aparecen van en la versión 1.
  EOT
  type        = map(number)
  default     = {}

  validation {
    condition = alltrue([for key in keys(var.rotation) : contains([
      "realtime-ticket-secret",
      "device-token-secret",
      "redis-auth-token",
      "database-api-password",
      "database-worker-password",
      "cloudfront-origin-header",
    ], key)])
    error_message = "Cada clave de rotation tiene que ser un secreto generado: una mal escrita no rotaría nada."
  }
}
