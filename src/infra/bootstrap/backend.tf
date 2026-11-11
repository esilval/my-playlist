# Estado del arranque en el bucket que crea él mismo (ADR-0016, D17). Se migró con
# `terraform init -migrate-state` tras el primer apply; ver src/infra/README.md.
terraform {
  backend "s3" {
    bucket       = "myplaylist-200oklabs-terraform-state"
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }
}
