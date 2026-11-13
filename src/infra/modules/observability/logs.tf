# Un grupo por tarea, 30 días todos (R016, ADR-0020). La preproducción añade Mailpit y k6
# (D13). El cómputo los recibe en `log_groups`.
locals {
  production = var.environment == "production"
  namespace  = "MyPlaylist/${var.environment}"
  log_tasks  = concat(["api", "worker", "realtime", "migrate"], local.production ? [] : ["mailpit", "k6"])
}

resource "aws_cloudwatch_log_group" "this" {
  for_each = toset(local.log_tasks)

  name              = "/myplaylist/${var.environment}/${each.key}"
  retention_in_days = 30
}
