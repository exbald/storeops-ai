output "api_service_url" {
  description = "Public URL of the deployed StoreOps API service"
  value       = google_cloud_run_v2_service.api.uri
}

output "worker_service_url" {
  description = "Private URL of the StoreOps Worker service"
  value       = google_cloud_run_v2_service.worker.uri
}

output "media_bucket_name" {
  description = "Name of the Google Cloud Storage bucket for media assets"
  value       = google_storage_bucket.media.name
}

output "bigquery_dataset_id" {
  description = "BigQuery dataset ID for analytics"
  value       = google_bigquery_dataset.analytics.dataset_id
}

output "api_service_account_email" {
  description = "Service account email for the public API"
  value       = google_service_account.api.email
}

output "worker_service_account_email" {
  description = "Service account email for the private worker"
  value       = google_service_account.worker.email
}

output "invoker_service_account_email" {
  description = "Service account email for invoking private worker and scheduler"
  value       = google_service_account.invoker.email
}
