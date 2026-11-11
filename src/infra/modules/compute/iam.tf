# Permisos de cada tarea (D5, D6). El rol de ejecución, que usa ECS para arrancarla, solo
# lee los secretos de esa tarea: el del usuario maestro, solo la migración. El rol de la
# tarea, que usa la aplicación, solo puede enviar correo en el trabajador (D14).
data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  for_each = local.tasks

  name               = "${var.name}-${each.key}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  for_each = local.tasks

  role       = aws_iam_role.execution[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "read_secrets" {
  for_each = local.tasks

  statement {
    actions = ["secretsmanager:GetSecretValue"]
    # Sin el sufijo `:clave::` de los valores que salen de un secreto JSON.
    resources = distinct([for arn in values(each.value.secrets) : trimsuffix(trimsuffix(arn, ":username::"), ":password::")])
  }
}

resource "aws_iam_role_policy" "read_secrets" {
  for_each = local.tasks

  name   = "read-secrets"
  role   = aws_iam_role.execution[each.key].id
  policy = data.aws_iam_policy_document.read_secrets[each.key].json
}

resource "aws_iam_role" "task" {
  for_each = local.tasks

  name               = "${var.name}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "send_email" {
  statement {
    actions   = ["ses:SendEmail"]
    resources = ["*"]

    condition {
      test     = "StringLike"
      variable = "ses:FromAddress"
      values   = ["*@${var.domain}"]
    }
  }
}

resource "aws_iam_role_policy" "send_email" {
  name   = "send-email"
  role   = aws_iam_role.task["worker"].id
  policy = data.aws_iam_policy_document.send_email.json
}
