variable "name" {
  description = "Prefijo de los nombres: `myplaylist-<entorno>`."
  type        = string
}

variable "production" {
  description = "Producción protege la base contra el borrado y guarda una instantánea final; la preproducción temporal no (D13)."
  type        = bool
}

variable "private_subnet_ids" {
  description = "Las subredes privadas, una por zona (D2)."
  type        = list(string)
}

variable "data_security_group_id" {
  description = "El grupo que solo admite a las tareas (D2)."
  type        = string
}

variable "db_instance_class" {
  description = "Clase de RDS (D4). La prueba de carga dice si basta (R017)."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "GiB iniciales de gp3; crecen solos hasta `db_max_allocated_storage`."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  type    = number
  default = 100
}

variable "cache_node_type" {
  description = "Clase de los nodos de ElastiCache (D4)."
  type        = string
  default     = "cache.t4g.small"
}

variable "redis_auth_token" {
  description = <<-EOT
    Token de Redis. Es efímero: llega del módulo de secretos y se escribe con un atributo de
    solo escritura, así que no queda en el estado (D6).
  EOT
  type        = string
  sensitive   = true
  ephemeral   = true
  # Sin token, ElastiCache crearía Redis con TLS pero sin AUTH: no se admite.
  nullable = false

  validation {
    condition     = length(var.redis_auth_token) >= 16 && length(var.redis_auth_token) <= 128
    error_message = "El token de Redis tiene entre 16 y 128 caracteres, como exige ElastiCache."
  }
}

variable "redis_auth_token_version" {
  description = "Se sube a mano para rotar el token (D6)."
  type        = number
  default     = 1
}
