terraform {
  backend "gcs" {
    bucket = "argon-tuner-396010-tfstate-1089042319319"
    prefix = "fulfillai/dev"
  }
}
