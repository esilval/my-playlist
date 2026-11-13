variable "name" {
  description = "Prefijo de los nombres: `myplaylist-<entorno>`."
  type        = string
}

variable "production" {
  description = "Producción conserva el bucket de la SPA al destruirse; la preproducción temporal lo vacía y lo borra (R022)."
  type        = bool
}

variable "domain" {
  description = "El dominio público del entorno, el de los QR: `myplaylist.200oklabs.com` (D1)."
  type        = string
}

variable "zone_id" {
  description = "La zona de Route 53 de `200oklabs.com`, del arranque (D17)."
  type        = string
}

variable "origin_domain" {
  description = "El nombre del ALB con su certificado propio, del módulo de cómputo: `origin.<dominio>` (D1)."
  type        = string
}

variable "origin_header_name" {
  description = "La cabecera que exige el ALB, del módulo de cómputo (D1)."
  type        = string
}

variable "origin_header_secret_arn" {
  description = "El secreto `cloudfront-origin-header`: su valor es el que exigen las reglas del ALB (D6)."
  type        = string
}
