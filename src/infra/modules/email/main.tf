locals {
  mail_from_domain = "mail.${var.domain}"
  # Easy DKIM da siempre tres claves.
  dkim_keys = 3
}

resource "aws_sesv2_email_identity" "domain" {
  email_identity = var.domain

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }
}

# Easy DKIM: tres CNAME que apuntan a las claves que publica SES. Se recorren por posición,
# porque los tokens no se conocen hasta crear la identidad.
resource "aws_route53_record" "dkim" {
  count = local.dkim_keys

  zone_id = var.zone_id
  name    = "${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.domain}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

# MAIL FROM propio: los rebotes vuelven a `mail.<dominio>`, y SPF lo autoriza a SES. Así el
# remitente y el MAIL FROM son del mismo dominio, y DMARC queda alineado también por SPF.
#
# Si SES no encuentra el MX, envía con su MAIL FROM por defecto en lugar de rechazar el
# correo: se pierde la alineación por SPF, pero DKIM mantiene DMARC, y el correo sale.
resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  email_identity         = aws_sesv2_email_identity.domain.email_identity
  mail_from_domain       = local.mail_from_domain
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}

resource "aws_route53_record" "mail_from_mx" {
  zone_id = var.zone_id
  name    = local.mail_from_domain
  type    = "MX"
  ttl     = 1800
  records = ["10 feedback-smtp.${var.region}.amazonses.com"]
}

resource "aws_route53_record" "mail_from_spf" {
  zone_id = var.zone_id
  name    = local.mail_from_domain
  type    = "TXT"
  ttl     = 1800
  records = ["v=spf1 include:amazonses.com -all"]
}

# DMARC (D14): lo que no pase SPF ni DKIM alineados va a correo no deseado.
resource "aws_route53_record" "dmarc" {
  zone_id = var.zone_id
  name    = "_dmarc.${var.domain}"
  type    = "TXT"
  ttl     = 1800
  records = ["v=DMARC1; p=quarantine; adkim=r; aspf=r"]
}

# Los rebotes y las quejas, al tema de avisos (D12, D14), sin las cabeceras del correo
# original, que llevan la dirección del destinatario (R016). El tema tiene que permitir
# publicar a SES (T016).
resource "aws_ses_identity_notification_topic" "this" {
  for_each = toset(["Bounce", "Complaint"])

  identity                 = aws_sesv2_email_identity.domain.email_identity
  notification_type        = each.key
  topic_arn                = var.alerts_topic_arn
  include_original_headers = false
}

# Con los dos avisos en el tema, SES deja de reenviarlos por correo: el remitente
# `no-responder@` no tiene buzón.
resource "aws_sesv2_email_identity_feedback_attributes" "this" {
  email_identity           = aws_sesv2_email_identity.domain.email_identity
  email_forwarding_enabled = false

  depends_on = [aws_ses_identity_notification_topic.this]
}
