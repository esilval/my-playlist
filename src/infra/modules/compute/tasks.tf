# Definiciones de tarea (D3, D5, D6, D8). Los secretos llegan siempre en `secrets`, con el
# ARN, y ECS los inyecta al arrancar: su valor no está en la definición, ni en la imagen,
# ni en el estado (R006).
locals {
  # La API y el tiempo real están detrás del ALB; el trabajador, no.
  web_services = {
    api      = { short_name = "api", port = 8000, health_path = "/api/health", path = "/api/*", priority = 10 }
    realtime = { short_name = "rt", port = 3001, health_path = "/health", path = "/socket.io/*", priority = 20 }
  }

  youtube = lookup(var.app_environment, "CATALOG_PROVIDER", "") == "youtube"

  # Lo que validan las dos configuraciones de producción y preproducción (D7). La clave de
  # YouTube solo va con el catálogo real: en preproducción su secreto no tiene valor, y ECS
  # no arranca una tarea que pide un secreto vacío.
  app_secrets = merge(
    {
      REALTIME_TICKET_SECRET = var.secret_arns["realtime-ticket-secret"]
      DEVICE_TOKEN_SECRET    = var.secret_arns["device-token-secret"]
    },
    local.youtube ? { YOUTUBE_API_KEY = var.secret_arns["youtube-api-key"] } : {},
  )

  database_environment = {
    DATABASE_HOST = var.database.host
    DATABASE_PORT = tostring(var.database.port)
    DATABASE_NAME = var.database.name
  }
  redis_environment = {
    REDIS_HOST = var.redis.host
    REDIS_PORT = tostring(var.redis.port)
  }
  region_environment = { AWS_REGION = var.region }

  tasks = {
    api = {
      image   = "api"
      command = null # el de la imagen: app.ops.env y uvicorn, sin migrar (D3, D8)
      port    = 8000
      environment = merge(var.app_environment, local.region_environment, local.database_environment, local.redis_environment, {
        DATABASE_USER = "myplaylist_api"
        API_WORKERS   = tostring(var.api_workers)
      })
      secrets = merge(local.app_secrets, {
        DATABASE_PASSWORD = var.secret_arns["database-api-password"]
        REDIS_AUTH_TOKEN  = var.secret_arns["redis-auth-token"]
      })
    }
    worker = {
      image   = "api"
      command = ["python", "-m", "app.ops.env", "python", "-m", "app.worker"]
      port    = null
      environment = merge(var.app_environment, local.region_environment, local.database_environment, local.redis_environment, {
        DATABASE_USER = "myplaylist_worker"
      })
      secrets = merge(local.app_secrets, {
        DATABASE_PASSWORD = var.secret_arns["database-worker-password"]
        REDIS_AUTH_TOKEN  = var.secret_arns["redis-auth-token"]
      })
    }
    # La única que migra, y la única con el usuario maestro (D5, D8). La lanza el flujo de
    # despliegue antes de actualizar los servicios.
    migrate = {
      image       = "api"
      command     = ["python", "-m", "app.ops.env", "sh", "-c", "alembic upgrade head && exec python -m app.ops.db_users"]
      port        = null
      environment = merge(var.app_environment, local.region_environment, local.database_environment)
      secrets = merge(local.app_secrets, {
        DATABASE_USER            = "${var.master_user_secret_arn}:username::"
        DATABASE_PASSWORD        = "${var.master_user_secret_arn}:password::"
        DATABASE_API_PASSWORD    = var.secret_arns["database-api-password"]
        DATABASE_WORKER_PASSWORD = var.secret_arns["database-worker-password"]
      })
    }
    # La imagen de Node no tiene app.ops.env: el mando compone REDIS_URL con el token, que
    # solo lleva letras, números y `-_` (D6), así que va en la URL sin escapar.
    realtime = {
      image   = "realtime"
      command = ["sh", "-c", "export REDIS_URL=\"rediss://:$${REDIS_AUTH_TOKEN}@$${REDIS_HOST}:$${REDIS_PORT}/0\" && exec node dist/server.js"]
      port    = 3001
      environment = merge(local.region_environment, local.redis_environment, {
        ENV  = var.app_environment["ENV"]
        PORT = "3001"
      })
      secrets = {
        REALTIME_TICKET_SECRET = var.secret_arns["realtime-ticket-secret"]
        REDIS_AUTH_TOKEN       = var.secret_arns["redis-auth-token"]
      }
    }
  }

  task_size = {
    api      = var.capacity.api
    worker   = var.capacity.worker
    realtime = var.capacity.realtime
    migrate  = { cpu = 512, memory = 1024 }
  }
}

resource "aws_ecs_task_definition" "this" {
  for_each = local.tasks

  family                   = "${var.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.task_size[each.key].cpu
  memory                   = local.task_size[each.key].memory
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = each.key
    image     = "${aws_ecr_repository.this[each.value.image].repository_url}:${var.image_tag}"
    essential = true
    command   = each.value.command
    portMappings = each.value.port == null ? [] : [{
      containerPort = each.value.port
      protocol      = "tcp"
    }]
    environment = [for key in sort(keys(each.value.environment)) : { name = key, value = each.value.environment[key] }]
    secrets     = [for key in sort(keys(each.value.secrets)) : { name = key, valueFrom = each.value.secrets[key] }]
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
