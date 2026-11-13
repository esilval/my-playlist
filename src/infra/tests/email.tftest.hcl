# Pruebas del correo (feature 004, T015, plan D14), sin AWS: el proveedor está simulado,
# así que `apply` no crea nada real.
mock_provider "aws" {
  mock_resource "aws_sesv2_email_identity" {
    defaults = {
      arn = "arn:aws:ses:us-east-2:955519187424:identity/myplaylist.200oklabs.com"
      # Un bloque que se configura se simula como objeto: se aplica a cada elemento.
      dkim_signing_attributes = {
        current_signing_key_length = "RSA_2048_BIT"
        signing_attributes_origin  = "AWS_SES"
        status                     = "PENDING"
        tokens                     = ["clave1", "clave2", "clave3"]
      }
    }
  }
}

variables {
  domain           = "myplaylist.200oklabs.com"
  zone_id          = "Z0639081273LJQWTITRKS"
  alerts_topic_arn = "arn:aws:sns:us-east-2:955519187424:myplaylist-production-alerts"
}

run "F004_R008_identidad_con_dkim_mail_from_y_dmarc" {
  command = apply

  module {
    source = "./modules/email"
  }

  assert {
    condition = (
      aws_sesv2_email_identity.domain.email_identity == "myplaylist.200oklabs.com" &&
      aws_sesv2_email_identity.domain.dkim_signing_attributes[0].next_signing_key_length == "RSA_2048_BIT"
    )
    error_message = "SES verifica el dominio del remitente con Easy DKIM de 2048 bits (D14)."
  }

  assert {
    condition = (
      [for record in aws_route53_record.dkim : record.name] == [
        "clave1._domainkey.myplaylist.200oklabs.com",
        "clave2._domainkey.myplaylist.200oklabs.com",
        "clave3._domainkey.myplaylist.200oklabs.com",
      ] &&
      [for record in aws_route53_record.dkim : one(record.records)] == [
        "clave1.dkim.amazonses.com", "clave2.dkim.amazonses.com", "clave3.dkim.amazonses.com",
      ] &&
      alltrue([for record in aws_route53_record.dkim : record.type == "CNAME" && record.zone_id == "Z0639081273LJQWTITRKS"])
    )
    error_message = "Las tres claves de DKIM se publican como CNAME en la zona (D14)."
  }

  assert {
    condition = (
      aws_sesv2_email_identity_mail_from_attributes.domain.mail_from_domain == "mail.myplaylist.200oklabs.com" &&
      aws_route53_record.mail_from_mx.name == "mail.myplaylist.200oklabs.com" &&
      aws_route53_record.mail_from_mx.records == toset(["10 feedback-smtp.us-east-2.amazonses.com"]) &&
      aws_route53_record.mail_from_spf.name == "mail.myplaylist.200oklabs.com" &&
      aws_route53_record.mail_from_spf.records == toset(["v=spf1 include:amazonses.com -all"])
    )
    error_message = "El MAIL FROM es mail.<dominio>, con su MX de SES en us-east-2 y su SPF (D14, ADR-0019)."
  }

  assert {
    condition = (
      aws_route53_record.dmarc.name == "_dmarc.myplaylist.200oklabs.com" &&
      aws_route53_record.dmarc.type == "TXT" &&
      startswith(one(aws_route53_record.dmarc.records), "v=DMARC1; p=quarantine;")
    )
    error_message = "DMARC con p=quarantine en el dominio del remitente (D14)."
  }

  assert {
    condition     = output.sender == "MyPlaylist <no-responder@myplaylist.200oklabs.com>"
    error_message = "El remitente es no-responder@ del dominio verificado (D14)."
  }
}

run "F004_R008_rebotes_y_quejas_van_al_tema_de_avisos" {
  command = apply

  module {
    source = "./modules/email"
  }

  assert {
    condition = (
      toset(keys(aws_ses_identity_notification_topic.this)) == toset(["Bounce", "Complaint"]) &&
      alltrue([
        for topic in aws_ses_identity_notification_topic.this :
        topic.identity == "myplaylist.200oklabs.com" &&
        topic.topic_arn == "arn:aws:sns:us-east-2:955519187424:myplaylist-production-alerts"
      ])
    )
    error_message = "Los rebotes y las quejas llegan al tema de avisos (D12, D14)."
  }

  assert {
    condition     = alltrue([for topic in aws_ses_identity_notification_topic.this : !topic.include_original_headers])
    error_message = "Los avisos no llevan las cabeceras del correo original, con la dirección del destinatario (R016)."
  }

  assert {
    condition     = !aws_sesv2_email_identity_feedback_attributes.this.email_forwarding_enabled
    error_message = "Los avisos van solo al tema, no por correo a un remitente sin buzón (D14)."
  }
}
