# Pruebas del arranque (feature 004, T009), sin AWS: el proveedor está simulado, así que
# `apply` no crea nada real.
mock_provider "aws" {
  # Los ARN de los recursos simulados tienen que tener forma de ARN.
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "955519187424"
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::myplaylist-200oklabs-terraform-state"
    }
  }
}

run "F004_R002_el_rol_de_despliegue_solo_se_asume_desde_los_entornos_de_este_repositorio" {
  command = apply

  module {
    source = "./bootstrap"
  }

  assert {
    condition = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == [
      "repo:esilval/my-playlist:environment:production",
      "repo:esilval/my-playlist:environment:preproduction",
    ]
    error_message = "El rol de despliegue tiene que limitarse a los entornos protegidos de este repositorio."
  }

  assert {
    condition     = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "El token de GitHub tiene que ir dirigido a STS."
  }

  assert {
    condition     = length(jsondecode(aws_iam_role.deploy.assume_role_policy).Statement) == 1 && jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Action == "sts:AssumeRoleWithWebIdentity"
    error_message = "El rol de despliegue no puede tener otra forma de asumirse."
  }

  # Una rama, un PR o una etiqueta fuera de un entorno no casan con la condición: el `sub`
  # de su token es `repo:…:ref:…` o `repo:…:pull_request`, nunca `environment:…`.
  assert {
    condition = alltrue([
      for subject in jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] :
      startswith(subject, "repo:esilval/my-playlist:environment:")
    ])
    error_message = "Ningún sujeto del rol de despliegue puede ser una rama, un PR o un comodín."
  }
}

run "F004_R002_el_rol_de_plan_es_de_solo_lectura" {
  command = apply

  module {
    source = "./bootstrap"
  }

  assert {
    condition     = aws_iam_role_policy_attachment.plan_read_only.policy_arn == "arn:aws:iam::aws:policy/ReadOnlyAccess"
    error_message = "El rol de plan solo puede tener la política de solo lectura."
  }

  assert {
    condition     = jsondecode(aws_iam_role.plan.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == ["repo:esilval/my-playlist:pull_request"]
    error_message = "El rol de plan solo lo asumen los PR de este repositorio."
  }

  # Sobre el estado solo lee, salvo el archivo de bloqueo: cualquier acción que no sea de
  # lectura tiene que ir, y solo, contra `*.tflock`, sea cual sea su Sid.
  assert {
    condition = alltrue([
      for statement in jsondecode(aws_iam_role_policy.plan_state.policy).Statement :
      statement.Effect == "Allow" && (
        length(setsubtract(toset(flatten([statement.Action])), toset(["s3:ListBucket", "s3:GetObject"]))) == 0 ||
        (
          length(setsubtract(toset(flatten([statement.Action])), toset(["s3:PutObject", "s3:DeleteObject"]))) == 0 &&
          toset(flatten([statement.Resource])) == toset(["arn:aws:s3:::myplaylist-200oklabs-terraform-state/*.tflock"])
        )
      )
    ])
    error_message = "El rol de plan solo puede leer el estado y escribir su archivo de bloqueo."
  }
}

run "F004_R002_sin_crear_el_proveedor_oidc_los_roles_lo_referencian_por_su_arn" {
  command = apply

  module {
    source = "./bootstrap"
  }

  variables {
    create_github_oidc_provider = false
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "Sin la excepción de la organización, el arranque no intenta crear el proveedor OIDC (D18)."
  }

  assert {
    condition = alltrue([
      for policy in [aws_iam_role.deploy.assume_role_policy, aws_iam_role.plan.assume_role_policy] :
      jsondecode(policy).Statement[0].Principal.Federated == "arn:aws:iam::955519187424:oidc-provider/token.actions.githubusercontent.com"
    ])
    error_message = "Los dos roles confían en el proveedor OIDC de GitHub de la cuenta, por su ARN fijo."
  }
}

run "con_la_excepcion_el_arranque_crea_el_proveedor_oidc" {
  command = apply

  module {
    source = "./bootstrap"
  }

  variables {
    create_github_oidc_provider = true
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 1 && one(aws_iam_openid_connect_provider.github).client_id_list == toset(["sts.amazonaws.com"])
    error_message = "Con la excepción, el arranque crea el proveedor OIDC con la audiencia de STS."
  }

  assert {
    condition     = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Principal.Federated == one(aws_iam_openid_connect_provider.github).arn
    error_message = "El rol de despliegue confía en el proveedor que crea el arranque."
  }
}

run "el_estado_es_privado_cifrado_y_con_versiones" {
  command = apply

  module {
    source = "./bootstrap"
  }

  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "El bucket del estado tiene que guardar versiones."
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "El bucket del estado no puede ser público."
  }

  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "El estado tiene que estar cifrado."
  }

  assert {
    condition     = aws_route53_zone.domain.name == "200oklabs.com"
    error_message = "La zona es la del dominio del servicio."
  }

  assert {
    condition     = var.region == "us-east-2"
    error_message = "La región por defecto es la única que permite la organización (ADR-0019)."
  }
}
