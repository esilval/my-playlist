# Pruebas de los secretos (feature 004, T012, plan D6), sin AWS: el proveedor de AWS está
# simulado, y el de `random` genera los valores en local, sin guardarlos.
mock_provider "aws" {}

variables {
  name       = "myplaylist/test"
  production = true
}

run "F004_R006_los_secretos_generados_tienen_48_caracteres" {
  command = apply

  module {
    source = "./modules/secrets"
  }

  assert {
    condition     = output.secret_length == 48
    error_message = "Los secretos generados tienen 48 caracteres (D6): más de los 32 que exigen la API y C6."
  }

  assert {
    condition = toset(keys(aws_secretsmanager_secret_version.generated)) == toset([
      "database-api-password",
      "database-worker-password",
      "device-token-secret",
      "realtime-ticket-secret",
      "redis-auth-token",
      "cloudfront-origin-header",
    ])
    error_message = "Terraform genera los secretos de D5 y D6, y ninguno más."
  }
}

run "F004_R006_youtube_api_key_no_tiene_valor_en_terraform" {
  command = apply

  module {
    source = "./modules/secrets"
  }

  assert {
    condition     = contains(keys(aws_secretsmanager_secret.this), "youtube-api-key") && !contains(keys(aws_secretsmanager_secret_version.generated), "youtube-api-key")
    error_message = "La clave de YouTube tiene su secreto, pero el valor lo introduce una persona fuera de Terraform."
  }

  assert {
    condition     = output.secret_arns["youtube-api-key"] == aws_secretsmanager_secret.this["youtube-api-key"].arn
    error_message = "Las tareas reciben el ARN del secreto, nunca su valor."
  }
}

run "F004_R006_los_secretos_se_escriben_con_solo_escritura" {
  command = apply

  module {
    source = "./modules/secrets"
  }

  assert {
    condition = alltrue([
      for version in aws_secretsmanager_secret_version.generated :
      version.secret_string == null && version.secret_binary == null && version.secret_string_wo_version == 1
    ])
    error_message = "Cada versión se escribe con secret_string_wo: el estado no guarda el valor (D6)."
  }

  # `terraform test` no puede leer un recurso efímero ni un atributo de solo escritura.
  # Que los generados sean efímeros (`ephemeral "random_password"`, no `resource`) y usen
  # `secret_string_wo` lo comprueba el trabajo `infra` del CI, que busca en modules/ un
  # `resource "random_password"` o un `secret_string =`.

  assert {
    condition     = alltrue([for secret in aws_secretsmanager_secret.this : secret.recovery_window_in_days == 30])
    error_message = "En producción, un secreto borrado se puede recuperar durante 30 días."
  }
}

run "rotar_un_secreto_sube_su_version" {
  command = apply

  module {
    source = "./modules/secrets"
  }

  variables {
    rotation = { "redis-auth-token" = 2 }
  }

  assert {
    condition     = aws_secretsmanager_secret_version.generated["redis-auth-token"].secret_string_wo_version == 2 && aws_secretsmanager_secret_version.generated["device-token-secret"].secret_string_wo_version == 1
    error_message = "Subir la versión de un secreto solo rota ese (D6)."
  }
}

run "una_clave_de_rotacion_mal_escrita_no_se_admite" {
  command = plan

  module {
    source = "./modules/secrets"
  }

  variables {
    rotation = { "redis-token" = 2 }
  }

  expect_failures = [var.rotation]
}

run "F004_R022_la_preproduccion_borra_sus_secretos_al_momento" {
  command = apply

  module {
    source = "./modules/secrets"
  }

  variables {
    production = false
  }

  assert {
    condition     = alltrue([for secret in aws_secretsmanager_secret.this : secret.recovery_window_in_days == 0])
    error_message = "La preproducción no deja secretos en recuperación al destruirse (R022)."
  }
}
