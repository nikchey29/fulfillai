output "cluster_name" {
  value = google_container_cluster.fulfillai.name
}

output "region" {
  value = var.region
}

output "artifact_repository" {
  value = google_artifact_registry_repository.fulfillai.repository_id
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.fulfillai.repository_id}/fulfillai-api"
}
