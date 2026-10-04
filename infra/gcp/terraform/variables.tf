variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "europe-west3"
}

variable "cluster_name" {
  description = "GKE Autopilot cluster name."
  type        = string
  default     = "fulfillai-gke"
}

variable "environment" {
  description = "Environment label for cost and ownership tracking."
  type        = string
  default     = "dev"
}

variable "github_repository" {

  description = "GitHub repository allowed to federate into GCP."

  type = string

  default = "nikchey29/fulfillai"

}



variable "github_repository_id" {

  description = "Immutable GitHub repository ID used by the federation trust condition."

  type = string

  default = "1339347740"

}



variable "github_repository_owner_id" {

  description = "Immutable GitHub owner ID used by the federation trust condition."

  type = string

  default = "217042683"

}
