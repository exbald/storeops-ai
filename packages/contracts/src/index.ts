export * from "./api.js";
import type { components, operations, paths } from "./api.js";

export type Schemas = components["schemas"];
export type Operations = operations;
export type Paths = paths;

// Re-export core domain schema types for convenience
export type Store = Schemas["Store"];
export type Location = Schemas["Location"];
export type Product = Schemas["Product"];
export type Media = Schemas["Media"];
export type Import = Schemas["Import"];
export type Promotion = Schemas["Promotion"];
export type PolicyVersion = Schemas["PolicyVersion"];
export type Rule = Schemas["Rule"];
export type Visit = Schemas["Visit"];
export type Investigation = Schemas["Investigation"];
export type Action = Schemas["Action"];
export type Verification = Schemas["Verification"];
export type Report = Schemas["Report"];
export type Evidence = Schemas["Evidence"];
export type Job = Schemas["Job"];
export type JobEvent = Schemas["JobEvent"];
export type Metrics = Schemas["Metrics"];
export type ApiError = Schemas["Error"];
export type Workspace = Schemas["Workspace"];
export type Membership = Schemas["Membership"];
