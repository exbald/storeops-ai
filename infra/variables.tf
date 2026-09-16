variable "project_id" {
  description = "Explicit Google Cloud authorized project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud primary region for resources (e.g. asia-southeast1)"
  type        = string
  default     = "asia-southeast1"
}

variable "app_env" {
  description = "Application deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "gemini_model_id" {
  description = "Primary Gemini model ID per specs/01-architecture.md"
  type        = string
  default     = "gemini-3.8-flash"
}
