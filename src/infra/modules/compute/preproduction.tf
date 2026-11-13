# Solo en preproducción (D13): Mailpit, el buzón que recibe los correos de la API y el
# trabajador y que lee k6, y la definición de tarea de k6 para la prueba de carga (R017).
# Mailpit se registra en una zona DNS privada de la VPC (Cloud Map): así lo encuentran por
# nombre los servicios y también k6, que es una tarea suelta y no un servicio.
locals {
  preproduction = !var.production
  mailpit_ports = { smtp = 1025, http = 8025 }
  mailpit_host  = "mailpit.${var.name}.internal"
}

resource "aws_service_discovery_private_dns_namespace" "this" {
  count = local.preproduction ? 1 : 0

  name        = "${var.name}.internal"
  description = "Nombres internos de la preproducción (D13)"
  vpc         = var.vpc_id
}

resource "aws_service_discovery_service" "mailpit" {
  count = local.preproduction ? 1 : 0

  name = "mailpit"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.this[0].id
    routing_policy = "MULTIVALUE"

    dns_records {
      type = "A"
      ttl  = 10
    }
  }
}

# Mailpit y k6 no leen secretos ni usan AWS: les basta con bajar la imagen y escribir sus
# registros.
resource "aws_iam_role" "tools_execution" {
  count = local.preproduction ? 1 : 0

  name               = "${var.name}-tools-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "tools_execution" {
  count = local.preproduction ? 1 : 0

  role       = aws_iam_role.tools_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

locals {
  tools = local.preproduction ? {
    mailpit = {
      image       = var.mailpit_image
      cpu         = 256
      memory      = 512
      ports       = values(local.mailpit_ports)
      environment = {}
    }
    # La prueba de carga pasa por CloudFront y el ALB, como un cliente real (D13). T019 la
    # lanza con run-task y le da el guion.
    k6 = {
      image  = var.k6_image
      cpu    = 4096
      memory = 8192
      ports  = []
      environment = {
        API_URL        = "https://${var.domain}"
        ORIGIN         = "https://${var.domain}"
        MAILPIT_URL    = "http://${local.mailpit_host}:${local.mailpit_ports.http}"
        ESTABLISHMENTS = tostring(var.load_test_establishments)
      }
    }
  } : {}
}

resource "aws_ecs_task_definition" "tools" {
  for_each = local.tools

  family                   = "${var.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.tools_execution[0].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name         = each.key
    image        = each.value.image
    essential    = true
    portMappings = [for port in each.value.ports : { containerPort = port, protocol = "tcp" }]
    environment  = [for key in sort(keys(each.value.environment)) : { name = key, value = each.value.environment[key] }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = var.log_groups[each.key]
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
  }])
}

# Una sola tarea: es un buzón de pruebas, no tiene que aguantar la caída de una zona.
resource "aws_ecs_service" "mailpit" {
  count = local.preproduction ? 1 : 0

  name            = "mailpit"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.tools["mailpit"].arn
  desired_count   = 1
  launch_type     = "FARGATE"
  # Como los demás servicios: sus tareas llevan la etiqueta `environment`, con la que la
  # destrucción de la preproducción comprueba que no queda nada (R022).
  propagate_tags = "SERVICE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.tasks_security_group_id]
    assign_public_ip = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.mailpit[0].arn
  }
}
