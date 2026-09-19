// Mirrors backend schemas/lead.py.
export type LeadState = "PENDING" | "REACHED_OUT";

export interface Lead {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  state: LeadState;
  created_at: string;
  reached_out_at: string | null;
  reached_out_by: string | null;
}

export interface LeadList {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeadCreated {
  id: string;
}
