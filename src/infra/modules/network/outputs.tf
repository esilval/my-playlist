output "vpc_id" {
  value = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "El ALB y las tareas de ECS."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "RDS y ElastiCache."
  value       = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "tasks_security_group_id" {
  value = aws_security_group.tasks.id
}

output "data_security_group_id" {
  value = aws_security_group.data.id
}
