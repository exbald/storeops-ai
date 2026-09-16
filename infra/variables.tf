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

variable "budget_amount" {
  description = "Configurable development budget in USD"
  type        = number
  default     = 100.0
}

variable "budget_alert_email" {
  description = "Email recipient for budget threshold notifications"
  type        = string
  default     = ""
}

variable "gemini_model_id" {
  description = "Primary Gemini model ID"
  type        = string
  default     = "gemini-2.5-flash"
}
