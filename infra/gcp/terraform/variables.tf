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
