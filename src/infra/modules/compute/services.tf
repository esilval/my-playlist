# El clúster y los servicios (D3). Cada servicio reparte sus tareas entre las dos zonas y,
# si las nuevas no superan su comprobación de salud, ECS vuelve a la revisión anterior
# (R005). Terraform no deshace lo que cambian el despliegue (la definición de tarea) ni la
# retirada y el autoescalado (el número de tareas, D10).
resource "aws_ecs_cluster" "this" {
  name = var.name
}

locals {
  services = toset(["api", "worker", "realtime"])
}

resource "aws_ecs_service" "this" {
  for_each = local.services

  name                               = each.key
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.this[each.key].arn
  desired_count                      = var.capacity[each.key].min
  launch_type                        = "FARGATE"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  availability_zone_rebalancing      = "ENABLED"
  health_check_grace_period_seconds  = contains(keys(local.web_services), each.key) ? 60 : null
  propagate_tags                     = "SERVICE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Subredes públicas con IP pública, sin NAT; el grupo solo admite al ALB (D2).
  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.tasks_security_group_id]
    assign_public_ip = true
  }

  dynamic "load_balancer" {
    for_each = contains(keys(local.web_services), each.key) ? [local.web_services[each.key]] : []

    content {
      target_group_arn = aws_lb_target_group.this[each.key].arn
      container_name   = each.key
      container_port   = load_balancer.value.port
    }
  }

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }

  depends_on = [aws_lb_listener_rule.this]
}

# Autoescalado al 60 % de CPU entre el mínimo y el máximo (D3). El trabajador tiene los dos
# iguales, así que no escala.
resource "aws_appautoscaling_target" "this" {
  for_each = { for service in local.services : service => var.capacity[service] if var.capacity[service].max > var.capacity[service].min }

  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this[each.key].name}"
  min_capacity       = each.value.min
  max_capacity       = each.value.max
}

resource "aws_appautoscaling_policy" "cpu" {
  for_each = aws_appautoscaling_target.this

  name               = "${var.name}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = each.value.service_namespace
  scalable_dimension = each.value.scalable_dimension
  resource_id        = each.value.resource_id

  target_tracking_scaling_policy_configuration {
    target_value = 60

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}
