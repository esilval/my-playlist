locals {
  # Los que genera Terraform (D5, D6). Las tareas los reciben como `secrets` de su
  # definición (D6). ElastiCache lee el token de Redis de su secreto, con un recurso efímero
  # al componer el entorno (T017): así siempre coincide con lo guardado.
  generated = toset([
    "realtime-ticket-secret",   # REALTIME_TICKET_SECRET: API, trabajador y C6 (ADR-0014)
    "device-token-secret",      # DEVICE_TOKEN_SECRET: API (003, D3)
    "redis-auth-token",         # REDIS_AUTH_TOKEN: ElastiCache, API, trabajador y C6 (D4)
    "database-api-password",    # DATABASE_API_PASSWORD: myplaylist_api (D5)
    "database-worker-password", # DATABASE_WORKER_PASSWORD: myplaylist_worker (D5)
    "cloudfront-origin-header", # la cabecera que pone CloudFront y exige el ALB (D1)
  ])
  # Los que introduce una persona, una vez, con `aws secretsmanager put-secret-value`.
  manual = toset([
    "youtube-api-key", # YOUTUBE_API_KEY (ADR-0010)
  ])

  secret_length = 48
}

ephemeral "random_password" "generated" {
  for_each = local.generated

  length = local.secret_length
  # Solo letras, números y `-_`: valen en una URL (rediss://:token@…) y en cualquier
  # variable de entorno sin escapar nada.
  special          = true
  override_special = "-_"
}

resource "aws_secretsmanager_secret" "this" {
  for_each = setunion(local.generated, local.manual)

  name                    = "${var.name}/${each.key}"
  recovery_window_in_days = var.production ? 30 : 0
}

# Solo escritura: el valor viaja a Secrets Manager y no queda en el estado (D6).
resource "aws_secretsmanager_secret_version" "generated" {
  for_each = local.generated

  secret_id                = aws_secretsmanager_secret.this[each.key].id
  secret_string_wo         = ephemeral.random_password.generated[each.key].result
  secret_string_wo_version = lookup(var.rotation, each.key, 1)
}
