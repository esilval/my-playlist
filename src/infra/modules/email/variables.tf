variable "domain" {
  description = "El dominio del remitente: `myplaylist.200oklabs.com` (D14). No es el raíz, para no compartir su reputación."
  type        = string
}

variable "zone_id" {
  description = "La zona de Route 53 de `200oklabs.com`, del arranque (D17)."
  type        = string
}

variable "region" {
  description = "La región de SES (ADR-0019): da el anfitrión del MX del MAIL FROM."
  type        = string
  default     = "us-east-2"
}

variable "alerts_topic_arn" {
  description = "El tema de avisos del módulo de observabilidad: recibe los rebotes y las quejas (D12, D14)."
  type        = string
}
