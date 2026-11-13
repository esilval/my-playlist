output "identity_arn" {
  description = "La identidad de SES: el trabajador solo puede enviar desde ella (D14), y el tema de avisos admite a SES con ella como origen (T016)."
  value       = aws_sesv2_email_identity.domain.arn
}

output "sender" {
  description = "EMAIL_FROM de producción (D6)."
  value       = "MyPlaylist <no-responder@${var.domain}>"
}
