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


output "workload_service_account" {
  value = google_service_account.fulfillai_api.email
}

output "database_secret_name" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "github_workload_identity_provider" {

  description = "Full Workload Identity Provider name for GitHub Actions."

  value = google_iam_workload_identity_pool_provider.github.name

}



output "github_deployer_service_account" {

  description = "Service account impersonated by the FulfillAI GitHub Actions delivery workflow."

  value = google_service_account.github_deployer.email

}
