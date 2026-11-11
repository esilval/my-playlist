variable "name" {
  description = "Prefijo de los nombres: `myplaylist-<entorno>`."
  type        = string
}

variable "cidr_block" {
  description = "Rango de la VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "availability_zones" {
  description = "Las dos zonas de la región en que se reparte todo (Q3, D3, D4)."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2
    error_message = "Hacen falta exactamente dos zonas distintas."
  }
}

variable "service_ports" {
  description = "Puertos en que escuchan las tareas detrás del ALB: la API y el tiempo real (D3)."
  type        = map(number)
  default = {
    api      = 8000
    realtime = 3001
  }
}
