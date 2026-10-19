export type UserRole = "freelancer" | "pyme" | "admin";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  company_name: string | null;
  created_at: string;
}

export type ContractStatus = "uploaded" | "processing" | "analyzed" | "failed";

export interface Contract {
  id: number;
  original_filename: string;
  page_count: number | null;
  status: ContractStatus;
  global_risk_score: number | null;
  created_at: string;
}

export interface RegisterData {
  email: string;
  full_name: string;
  password: string;
  role: "freelancer" | "pyme";
  company_name?: string;
}