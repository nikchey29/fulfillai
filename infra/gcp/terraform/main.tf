resource "google_project_service" "required" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com"
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "fulfillai" {
  name                    = "fulfillai-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required]
}

resource "google_compute_subnetwork" "gke" {
  name          = "fulfillai-gke-subnet"
  region        = var.region
  network       = google_compute_network.fulfillai.id
  ip_cidr_range = "10.20.0.0/20"

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.24.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.28.0.0/20"
  }
}

resource "google_artifact_registry_repository" "fulfillai" {
  location      = var.region
  repository_id = "fulfillai"
  description   = "FulfillAI container images"
  format        = "DOCKER"
  depends_on    = [google_project_service.required]
}

resource "google_container_cluster" "fulfillai" {
  name     = var.cluster_name
  location = var.region

  enable_autopilot = true
  networking_mode  = "VPC_NATIVE"
  network           = google_compute_network.fulfillai.id
  subnetwork        = google_compute_subnetwork.gke.id

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  deletion_protection = false
  depends_on          = [google_project_service.required]
}
