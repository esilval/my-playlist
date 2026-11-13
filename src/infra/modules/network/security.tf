# Grupos de seguridad (D1, D2). Las reglas son recursos aparte para que cada una se pueda
# leer y probar sola.

# Las direcciones desde las que CloudFront llega a los orígenes (D1): el ALB solo las admite.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "ALB: solo desde CloudFront (D1)"
  vpc_id      = aws_vpc.this.id
}

# Una sola regla, en el 443: CloudFront habla con el ALB por HTTPS. Esta lista cuenta como
# 55 reglas en la cuota de 60 del grupo, así que no cabe una segunda que la use.
resource "aws_vpc_security_group_ingress_rule" "alb_from_cloudfront" {
  security_group_id = aws_security_group.alb.id
  description       = "CloudFront por HTTPS"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  for_each = var.service_ports

  security_group_id            = aws_security_group.alb.id
  description                  = "Hacia las tareas de ${each.key}"
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

# Las tareas de ECS: entran solo desde el ALB, a su puerto; salen a internet (D2).
resource "aws_security_group" "tasks" {
  name        = "${var.name}-tasks"
  description = "Tareas de ECS: solo desde el ALB (D2)"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  for_each = var.service_ports

  security_group_id            = aws_security_group.tasks.id
  description                  = "Desde el ALB hacia ${each.key}"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

# Solo en preproducción: la API y el trabajador envían a Mailpit, y k6 lee sus correos, todo
# entre tareas del mismo grupo (D13).
resource "aws_vpc_security_group_ingress_rule" "tasks_mailpit" {
  for_each = var.mailpit_ports

  security_group_id            = aws_security_group.tasks.id
  description                  = "Mailpit (${each.key}) entre las tareas"
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "tasks_out" {
  security_group_id = aws_security_group.tasks.id
  description       = "YouTube, SES, Secrets Manager, ECR, CloudWatch y los datos"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# RDS y ElastiCache: solo desde las tareas, y sin ninguna regla de salida (D2).
resource "aws_security_group" "data" {
  name        = "${var.name}-data"
  description = "RDS y ElastiCache: solo desde las tareas (D2)"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "data_from_tasks" {
  for_each = { postgres = 5432, redis = 6379 }

  security_group_id            = aws_security_group.data.id
  description                  = "${each.key} desde las tareas"
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}
