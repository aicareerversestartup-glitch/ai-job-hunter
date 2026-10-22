export interface User { id: number; email: string; full_name: string }

export interface Contact { full_name: string; email: string; phone: string; location: string; links: string[] }
export interface Experience { employer: string; title: string; location: string; start: string; end: string; employment_type?: string; bullets: string[] }
export interface Education { institution: string; degree: string; field: string; start: string; end: string; details: string[] }
export interface Project { name: string; description: string; bullets: string[]; technologies: string[]; link: string }
export interface CVData {
  contact: Contact; headline: string; summary: string; experience: Experience[]; education: Education[];
  skills: string[]; certifications: string[]; projects: Project[]; languages: string[];
  other_sections: Record<string, string[]>;
}

export interface MasterCV {
  id: number; version: number; original_filename: string; status: "needs_review" | "verified" | "superseded";
  is_active: boolean; parse_method: string; parse_notes: string[]; data: CVData; parsed_data: CVData;
  raw_text: string; created_at: string; verified_at: string | null;
}

export interface CandidateProfile {
  full_name: string; email: string; phone: string; location: string; linkedin_url: string; github_url: string;
  portfolio_url: string; headline: string; notice_period: string; earliest_start_date: string;
  salary_expectation: string; current_salary: string; work_authorized_countries: string[];
  needs_sponsorship_countries: string[]; willing_to_relocate: boolean; willing_to_travel: string; pronouns: string;
  saved_answers: Record<string, string>; eeo_default: string;
  date_of_birth: string; nationality: string; visa_status: string; driving_licence: string;
  photo_path: string; include_photo: boolean; relocation_statement: string; passport_status: string; referees: Referee[]; custom_layouts: CustomLayout[];
}

export interface Referee { name: string; title: string; company: string; email: string; phone: string; relationship: string }
export interface CustomLayout {
  id: string; name: string; section_order: string[]; max_pages: number; photo: boolean;
  personal_details: string[]; headings: Record<string, string>;
}
export interface CountryFormat {
  code: string; country: string; document_title: string; max_pages: number; photo: string;
  personal_details: string[]; section_order: string[]; summary_heading: string; date_style: string;
  signature_line: boolean; referees: string; tips: string[]; sources: string[];
}
export interface FormatCatalog { countries: CountryFormat[]; styles: { key: string; label: string }[]; custom_layouts: CustomLayout[] }

export interface JobPreferences {
  target_roles: string[]; preferred_countries: string[]; preferred_cities: string[];
  remote_preference: "any" | "remote_only" | "hybrid_ok" | "onsite_ok"; employment_types: string[];
  min_salary: number | null; salary_currency: string; seniority_levels: string[];
  work_authorized_countries: string[]; needs_sponsorship_countries: string[]; exclude_keywords: string[];
  exclude_companies: string[]; willing_to_relocate: boolean;
  target_companies: { name: string; countries: string[] }[]; min_apply_score: number;
  include_cv_roles: boolean; excluded_cv_roles: string[];
}

export interface ProfileIO { profile: CandidateProfile; preferences: JobPreferences; auto_discovery: boolean }

export interface MissingRequirement {
  label: "MISSING REQUIREMENT"; kind: string; requirement: string; importance: "required" | "preferred";
  detail: string; evidence: string;
}

export interface MatchResult {
  score: number; components: Record<string, number>; matched_skills: string[];
  missing_requirements: MissingRequirement[]; dealbreakers: string[]; reasons: string[];
  recommendation: "strong" | "good" | "stretch" | "poor"; years_experience: number;
}

export interface QualityFlag { code: string; points: number; message: string; kind: "fraud" | "quality" }
export interface Quality {
  risk_score: number; risk_level: "low" | "medium" | "high"; quality_score: number; flags: QualityFlag[];
  user_override?: boolean;
}

export interface JobRow {
  id: number; source: string; url: string; apply_url: string; title: string; company: string; location: string;
  country: string; remote_type: string; employment_type: string; seniority: string; posted_at: string | null;
  discovered_at: string; salary_min: number | null; salary_max: number | null; salary_currency: string;
  risk_level: string; status: string; quality: Quality; also_seen_on: { source: string; url: string }[];
  description_preview?: string; description_text?: string; snippet_only?: boolean;
  jd_sections?: { key: string; label: string; lines: string[] }[];
  match: null | {
    score: number; recommendation: string; missing_count?: number; matched_skills?: string[];
    dealbreakers?: string[]; result?: MatchResult; priority?: Priority;
  };
}

export interface Violation { code: string; location: string; message: string; value: string; severity: "error" | "warning" }
export interface GuardReport { passed: boolean; violations: Violation[] }

export interface Answer {
  question: string; answer: string; needs_user_input: boolean; source: string; skip?: boolean; guard?: GuardReport;
}

export interface AppEvent {
  id: number; kind: string; from_status: string; to_status: string; details: Record<string, unknown>;
  occurred_at: string;
}

export interface ApplyOutcome {
  status: string; message: string; blocker: { kind: string; detail: string } | null; filled: string[];
  unfilled: string[]; screenshot: string; final_url: string;
}

export interface Application {
  id: number; job_id: number; status: string; match_score: number; tailored_cv: CVData; cv_guard: GuardReport;
  cover_letter: string; cover_guard: GuardReport; answers: Answer[];
  cv_format: CvFormatChoice; format_notes: string[]; generation_notes: string[];
  generation_method: Record<string, string>; approved_at: string | null; submitted_at: string | null;
  submission_method: string; apply_url: string; notes: string; created_at: string; updated_at: string;
  blocker: { auto_submit_requested?: boolean; last_outcome?: ApplyOutcome };
  job: JobRow & { description_text: string }; match: MatchResult | null; master_cv: CVData | null;
  events: AppEvent[]; approval_valid: boolean; approval_blockers: string[]; auto_submit_available: boolean;
  apply_assist_available: boolean;
}

export interface ApplicationRow {
  id: number; status: string; match_score: number; job_id: number; title: string; company: string; location: string;
  apply_url: string; created_at: string; updated_at: string; submitted_at: string | null; needs_attention: boolean;
}

export interface JobSource {
  id: number; kind: string; identifier: string; label: string; enabled: boolean; last_run_at: string | null;
  last_status: string; last_error: string; last_count: number;
}
export interface SourceType { kind: string; name: string; needs_identifier: boolean; identifier_help: string; terms_note: string }

export interface DiscoveryRun {
  id: number; trigger: string; status: string; started_at: string; finished_at: string | null;
  stats: Record<string, number>; errors: { source: string; error: string }[];
}

export interface Dashboard {
  cv_status: string; jobs_total: number; jobs_this_week: number; strong_matches: number;
  applications_by_status: Record<string, number>; awaiting_review: number; needs_action: number; submitted: number;
  interviews: number; offers: number; response_rate: number | null; interview_rate: number | null;
  interviewed: number; follow_ups_due: number; pending_emails: number;
}

export interface AISettings { provider: string; model: string; base_url: string; api_key_masked: string; temperature: number; source: string }

export interface TargetCompany {
  name: string; countries: string[]; careers_url: string; industry: string; sponsorship_note: string;
  suggested_roles: string[];
  sources: { id: number; kind: string; identifier: string; enabled: boolean; last_status: string; last_error: string;
             last_count: number; detection: string }[];
}
export interface RegistryCompany { name: string; industry: string; careers_url: string; hubs: string[]; sponsorship_note: string; roles: string[] }

export interface InboxSettings {
  configured: boolean; provider: string; host: string; port: number; username: string; enabled: boolean;
  has_password: boolean; last_checked_at: string | null; last_status: string; last_error: string;
}
export interface EmailDetection {
  event_id: number; application_id: number; company: string; title: string; status: string; occurred_at: string;
  classification: string; subject: string; from: string; evidence: string; suggested_status: string;
  resolved: boolean; applied?: boolean;
}
export interface FollowUp { due: boolean; days_since_submitted: number; already_followed_up: boolean; subject: string; body: string }

export interface CvFormatChoice {
  country_code: string; style: string; custom_layout_id: string; date_precision?: string; layout?: string; job_country?: string;
}

export interface Priority { country_rank: number; in_country_list: boolean; role_tier: number; matched_role: string; rank: number }
export interface BatchStatus { running: boolean; total?: number; done?: number; created?: number[];
  errors?: { job_id: number; error: string }[]; skipped?: Record<string, number> }

export interface BillingStatus {
  plan: "free" | "pro"; plan_expires_at: string | null; plan_source: string; show_ads: boolean;
  drafts_per_day: number; drafts_used_today: number; searches_per_day: number; searches_used_today: number;
  bonus_today: number; reward_ads_left: number; reward_ad_bonus: number; server_ai: boolean;
  referral_code: string | null; referral_pro_days: number;
  limits: { free_drafts: number; pro_drafts: number; free_searches: number; pro_searches: number };
  purchases: { ios: string; android: string; web: string; entitlement: string };
}
export interface Partner { id: string; name: string; category: string; description: string; countries: string[]; disclosure: string }
