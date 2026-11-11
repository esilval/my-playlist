# Pruebas de los datos (feature 004, T011, plan D4), sin AWS: el proveedor está simulado,
# así que `apply` no crea nada real.
mock_provider "aws" {
  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-2:955519187424:secret:rds!db-prueba", kms_key_id = "", secret_status = "active" }]
    }
  }
}

variables {
  name                   = "myplaylist-test"
  production             = true
  private_subnet_ids     = ["subnet-a", "subnet-b"]
  data_security_group_id = "sg-data"
  redis_auth_token       = "token-de-pruebas-de-48-caracteres-0123456789abcd"
}

run "F004_R009_rds_es_multi_az_y_redis_tiene_replica_con_conmutacion" {
  command = apply

  module {
    source = "./modules/data"
  }

  assert {
    condition     = aws_db_instance.postgres.multi_az && aws_db_instance.postgres.engine == "postgres" && aws_db_instance.postgres.engine_version == "16"
    error_message = "PostgreSQL 16 en RDS Multi-AZ: si cae una zona, conmuta a la réplica (D4)."
  }

  assert {
    condition = (
      aws_elasticache_replication_group.redis.num_cache_clusters == 2 &&
      aws_elasticache_replication_group.redis.multi_az_enabled &&
      aws_elasticache_replication_group.redis.automatic_failover_enabled
    )
    error_message = "Redis tiene una réplica en otra zona y conmuta solo (D4)."
  }

  assert {
    condition     = aws_elasticache_replication_group.redis.engine == "redis" && aws_elasticache_replication_group.redis.engine_version == "7.1"
    error_message = "Redis OSS 7.1: EXPIRE NX lo exige (ADR-0004)."
  }

  assert {
    condition = (
      !aws_db_instance.postgres.publicly_accessible &&
      aws_db_instance.postgres.vpc_security_group_ids == toset(["sg-data"]) &&
      aws_elasticache_replication_group.redis.security_group_ids == toset(["sg-data"]) &&
      aws_db_subnet_group.this.subnet_ids == toset(["subnet-a", "subnet-b"]) &&
      aws_elasticache_subnet_group.this.subnet_ids == toset(["subnet-a", "subnet-b"])
    )
    error_message = "Los dos viven en las subredes privadas, con el grupo de los datos y sin acceso público (D2)."
  }
}

run "F004_R010_rds_guarda_copias_7_dias" {
  command = apply

  module {
    source = "./modules/data"
  }

  assert {
    condition     = aws_db_instance.postgres.backup_retention_period == 7
    error_message = "Las copias se guardan 7 días, con restauración a cualquier momento (R010)."
  }

  assert {
    condition     = aws_db_instance.postgres.storage_encrypted && aws_db_instance.postgres.manage_master_user_password
    error_message = "La base está cifrada, y la contraseña maestra la gestiona RDS (D4, D5)."
  }
}

run "F004_R010_produccion_protege_contra_borrado_y_guarda_instantanea_final" {
  command = apply

  module {
    source = "./modules/data"
  }

  assert {
    condition     = aws_db_instance.postgres.deletion_protection && !aws_db_instance.postgres.skip_final_snapshot && aws_db_instance.postgres.final_snapshot_identifier == "myplaylist-test-final"
    error_message = "En producción, la base no se puede borrar sin quitar la protección, y deja una instantánea final."
  }
}

run "F004_R022_la_preproduccion_se_destruye_sin_dejar_nada" {
  command = apply

  module {
    source = "./modules/data"
  }

  variables {
    production = false
  }

  assert {
    condition     = !aws_db_instance.postgres.deletion_protection && aws_db_instance.postgres.skip_final_snapshot && aws_db_instance.postgres.final_snapshot_identifier == null
    error_message = "La preproducción temporal se destruye sin protección ni instantánea final (D13)."
  }
}

run "F004_R009_redis_cifra_en_transito_y_exige_token" {
  command = apply

  module {
    source = "./modules/data"
  }

  assert {
    condition     = aws_elasticache_replication_group.redis.transit_encryption_enabled && aws_elasticache_replication_group.redis.at_rest_encryption_enabled
    error_message = "Redis cifra en tránsito y en reposo (D4)."
  }

  # El token se escribe con el atributo de solo escritura: el estado no lo guarda (D6). Que
  # se exija lo garantizan `nullable = false`, que Terraform aplica antes de planificar (un
  # null da «Required variable not set»), y la validación de longitud de la run siguiente.
  assert {
    condition     = aws_elasticache_replication_group.redis.auth_token == null && aws_elasticache_replication_group.redis.auth_token_wo_version == 1
    error_message = "El token de Redis va por auth_token_wo, nunca por auth_token."
  }
}

run "F004_R009_un_token_de_redis_corto_no_se_admite" {
  command = plan

  module {
    source = "./modules/data"
  }

  variables {
    redis_auth_token = "corto"
  }

  expect_failures = [var.redis_auth_token]
}
