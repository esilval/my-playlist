# El estado de production, en el bucket del arranque (ADR-0016, D18).
bucket       = "myplaylist-200oklabs-terraform-state"
key          = "production/terraform.tfstate"
region       = "us-east-2"
encrypt      = true
use_lockfile = true
