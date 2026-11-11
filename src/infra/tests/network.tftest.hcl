# Pruebas de la red (feature 004, T010, plan D2), sin AWS: el proveedor está simulado, así
# que `apply` no crea nada real.
mock_provider "aws" {
  mock_data "aws_ec2_managed_prefix_list" {
    defaults = {
      id = "pl-3b927c52"
    }
  }
}

variables {
  name               = "myplaylist-test"
  availability_zones = ["us-east-2a", "us-east-2b"]
}

run "F004_R009_subredes_publicas_y_privadas_en_dos_zonas" {
  command = apply

  module {
    source = "./modules/network"
  }

  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.private) == 2
    error_message = "Hay dos subredes públicas y dos privadas."
  }

  assert {
    condition = (
      toset(aws_subnet.public[*].availability_zone) == toset(["us-east-2a", "us-east-2b"]) &&
      toset(aws_subnet.private[*].availability_zone) == toset(["us-east-2a", "us-east-2b"])
    )
    error_message = "Cada nivel tiene una subred en cada zona: la caída de una zona no deja sin servicio (Q3)."
  }

  assert {
    condition     = length(distinct(concat(aws_subnet.public[*].cidr_block, aws_subnet.private[*].cidr_block))) == 4
    error_message = "Las cuatro subredes tienen rangos distintos."
  }

  assert {
    condition     = alltrue([for subnet in concat(aws_subnet.public, aws_subnet.private) : !subnet.map_public_ip_on_launch])
    error_message = "Ninguna subred da IP pública por defecto: la pide cada servicio de ECS."
  }
}

run "F004_R009_los_datos_no_tienen_salida_a_internet" {
  command = apply

  module {
    source = "./modules/network"
  }

  # La tabla de las privadas no tiene ninguna ruta propia, y no hay NAT en el módulo.
  assert {
    condition     = length(aws_route_table.private.route) == 0
    error_message = "Las subredes privadas no tienen ruta a internet."
  }

  assert {
    condition     = toset(aws_route_table_association.private[*].route_table_id) == toset([aws_route_table.private.id])
    error_message = "Las dos subredes privadas usan la tabla sin salida."
  }

  assert {
    condition     = aws_route.public_internet.route_table_id == aws_route_table.public.id && aws_route.public_internet.gateway_id == aws_internet_gateway.this.id
    error_message = "La única ruta a internet es la de la tabla pública."
  }

  # Los datos no tienen ninguna regla de salida, ni aparte ni en línea.
  assert {
    condition     = length(aws_security_group.data.egress) == 0 && length(aws_security_group.data.ingress) == 0
    error_message = "El grupo de los datos no tiene reglas en línea ni salida."
  }

  # Los datos solo admiten conexiones desde las tareas, a sus dos puertos.
  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.data_from_tasks :
      rule.referenced_security_group_id == aws_security_group.tasks.id && rule.cidr_ipv4 == null
    ]) && toset([for rule in aws_vpc_security_group_ingress_rule.data_from_tasks : rule.from_port]) == toset([5432, 6379])
    error_message = "RDS y Redis solo admiten conexiones desde las tareas."
  }
}

# `terraform test` comprueba los recursos que nombra: un recurso nuevo (una regla en otro
# `aws_vpc_security_group_ingress_rule`, una `aws_route` aparte o un NAT) no lo vería. Por
# eso todas las reglas viven en los recursos que nombran estas pruebas, y lo demás es un
# control revisable de src/infra/README.md («Red»).
run "F004_R009_las_tareas_solo_admiten_entradas_desde_el_alb" {
  command = apply

  module {
    source = "./modules/network"
  }

  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.tasks_from_alb :
      rule.referenced_security_group_id == aws_security_group.alb.id && rule.cidr_ipv4 == null && rule.cidr_ipv6 == null
    ])
    error_message = "Las tareas solo admiten entradas desde el grupo del ALB."
  }

  assert {
    condition     = toset([for rule in aws_vpc_security_group_ingress_rule.tasks_from_alb : rule.from_port]) == toset([8000, 3001])
    error_message = "Solo se abren los puertos de la API y del tiempo real."
  }

  assert {
    condition     = length(aws_security_group.tasks.ingress) == 0 && length(aws_security_group.alb.ingress) == 0
    error_message = "Ni las tareas ni el ALB tienen reglas de entrada en línea."
  }

  # Y el ALB, a su vez, solo desde CloudFront (D1).
  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.alb_from_cloudfront.prefix_list_id == "pl-3b927c52" &&
      aws_vpc_security_group_ingress_rule.alb_from_cloudfront.cidr_ipv4 == null &&
      aws_vpc_security_group_ingress_rule.alb_from_cloudfront.from_port == 443
    )
    error_message = "El ALB solo admite la lista de prefijos de CloudFront, en el 443."
  }

  assert {
    condition     = data.aws_ec2_managed_prefix_list.cloudfront.name == "com.amazonaws.global.cloudfront.origin-facing"
    error_message = "La lista es la de los orígenes de CloudFront."
  }
}
