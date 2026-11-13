variable "name" {
  description = "Prefijo de los nombres: `myplaylist-<entorno>`."
  type        = string
}

variable "production" {
  description = "Producción conserva las imágenes de ECR al destruirse; la preproducción temporal las borra (R022)."
  type        = bool
}

variable "region" {
  description = "La región de los servicios y de SES (ADR-0019): `AWS_REGION` de las tareas (D6, D14)."
  type        = string
  default     = "us-east-2"
}

variable "domain" {
  description = "El dominio público del entorno, p. ej. `myplaylist.200oklabs.com`. El ALB atiende `origin.<dominio>` (D1)."
  type        = string
}

variable "public_validation_fqdn" {
  description = "El registro de validación del dominio público, que crea el módulo de borde: también valida el certificado del ALB (D1)."
  type        = string
}

variable "email_identity_arn" {
  description = "La identidad de SES del módulo de correo: la única desde la que envía el trabajador (D14). Sin ella, como en preproducción, que envía a Mailpit, nadie puede usar SES."
  type        = string
  default     = null
}

variable "zone_id" {
  description = "La zona de Route 53 de `200oklabs.com`, del arranque (D17)."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  description = "Las subredes públicas, una por zona: el ALB y las tareas (D2)."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) == 2
    error_message = "Hacen falta las dos subredes públicas, una por zona (Q3)."
  }
}

variable "alb_security_group_id" {
  type = string
}

variable "tasks_security_group_id" {
  type = string
}

variable "secret_arns" {
  description = "ARN de cada secreto del módulo de secretos, por nombre (D6)."
  type        = map(string)
}

variable "master_user_secret_arn" {
  description = "El secreto del usuario maestro de RDS: solo lo recibe la tarea de migración (D5, D8)."
  type        = string
}

variable "database" {
  description = "Dónde está PostgreSQL (D4)."
  type = object({
    host = string
    port = number
    name = string
  })
}

variable "redis" {
  description = "Dónde está Redis (D4)."
  type = object({
    host = string
    port = number
  })
}

variable "log_groups" {
  description = "Grupo de registros de cada tarea, que crea el módulo de observabilidad con 30 días (D12)."
  type        = map(string)

  validation {
    condition     = length(setsubtract(["api", "worker", "realtime", "migrate"], keys(var.log_groups))) == 0
    error_message = "Hace falta un grupo para api, worker, realtime y migrate."
  }
}

variable "image_tag" {
  description = "La etiqueta de las imágenes de las primeras definiciones de tarea. Después, cada despliegue registra las suyas (D9)."
  type        = string
}

variable "app_environment" {
  description = <<-EOT
    Configuración no secreta de la aplicación, igual para la API, el trabajador y la
    migración (D6): ENV, EMAIL_BACKEND, EMAIL_FROM, PUBLIC_BASE_URL, CATALOG_PROVIDER,
    DATA_POLICY_VERSION y, en preproducción, SMTP_HOST y SMTP_PORT.
  EOT
  type        = map(string)

  validation {
    condition     = contains(["preproduction", "production"], lookup(var.app_environment, "ENV", ""))
    error_message = "ENV tiene que ser preproduction o production (D7)."
  }

  validation {
    condition = length(setintersection(keys(var.app_environment), [
      "REALTIME_TICKET_SECRET", "DEVICE_TOKEN_SECRET", "YOUTUBE_API_KEY", "REDIS_AUTH_TOKEN",
      "DATABASE_PASSWORD", "DATABASE_API_PASSWORD", "DATABASE_WORKER_PASSWORD",
      "DATABASE_URL", "REDIS_URL",
    ])) == 0
    error_message = "Un secreto no va en app_environment: llega por secrets (D6, R006)."
  }
}

variable "capacity" {
  description = "Tareas y tamaño de cada servicio (D3). La prueba de carga fija los máximos (R017)."
  type = map(object({
    cpu    = number
    memory = number
    min    = number
    max    = number
  }))
  default = {
    api      = { cpu = 2048, memory = 4096, min = 2, max = 6 }
    worker   = { cpu = 256, memory = 512, min = 2, max = 2 }
    realtime = { cpu = 512, memory = 1024, min = 2, max = 4 }
  }

  validation {
    condition     = alltrue([for service in values(var.capacity) : service.min >= 2 && service.max >= service.min])
    error_message = "Cada servicio tiene al menos dos tareas, una por zona (Q3, R009)."
  }
}

variable "api_workers" {
  description = "Procesos de uvicorn por tarea de la API: tantos como vCPU (ADR-0015, D3)."
  type        = number
  default     = 2
}
