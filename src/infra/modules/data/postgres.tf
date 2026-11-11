resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "postgres" {
  identifier     = var.name
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  db_name  = "myplaylist"
  username = "myplaylist_admin"
  # El usuario maestro lo gestiona RDS en Secrets Manager: su contraseña no pasa por
  # Terraform (D4, D5). Solo lo usa la tarea de migración (D8).
  manage_master_user_password = true

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  # Dos zonas: si cae una, RDS conmuta a la réplica en 60 a 120 s (R009).
  multi_az               = true
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.data_security_group_id]
  publicly_accessible    = false

  # Restauración a cualquier momento de los últimos 7 días: pierde como mucho unos 5
  # minutos (R010).
  backup_retention_period = 7
  backup_window           = "07:00-08:00" # 2 a 3 de la mañana en Bogotá
  maintenance_window      = "sun:08:00-sun:09:00"
  copy_tags_to_snapshot   = true

  deletion_protection = var.production
  skip_final_snapshot = !var.production
  # Si producción se destruyera dos veces, la segunda fallaría porque esta instantánea ya
  # existe: antes hay que borrarla o renombrarla (src/infra/README.md).
  final_snapshot_identifier = var.production ? "${var.name}-final" : null

  auto_minor_version_upgrade = true
  apply_immediately          = !var.production
}
