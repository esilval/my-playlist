resource "aws_elasticache_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = var.name
  description          = "Cache, limites y eventos de MyPlaylist (ADR-0004)"

  engine         = "redis"
  engine_version = "7.1" # EXPIRE NX, que usa el límite de búsquedas (003) y la cuota (D11)
  node_type      = var.cache_node_type
  port           = 6379

  # Primario y réplica en zonas distintas, con conmutación automática (R009).
  num_cache_clusters         = 2
  multi_az_enabled           = true
  automatic_failover_enabled = true

  subnet_group_name  = aws_elasticache_subnet_group.this.name
  security_group_ids = [var.data_security_group_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  # Solo escritura: el token no queda en el estado de Terraform (D6).
  auth_token_wo         = var.redis_auth_token
  auth_token_wo_version = var.redis_auth_token_version

  snapshot_retention_limit = 1
  snapshot_window          = "06:00-07:00" # 1 a 2 de la mañana en Bogotá
  maintenance_window       = "sun:09:00-sun:10:00"
  # ElastiCache solo cambia el token de AUTH al momento: sin esto, la rotación de D6 no se
  # aplicaría en producción. Los demás cambios de este grupo también se aplican al momento.
  apply_immediately = true
}
