const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json() as Promise<T>
}

export interface Repo {
  id: number
  name: string
  created_at: string
}

export interface Flag {
  rule: string
  severity: "info" | "warning" | "critical"
  detail: string
}

export interface Commit {
  sha: string
  original_message: string | null
  rewritten_message: string | null
  amended: boolean
  score: number | null
  grade: string | null
  llm_aligned: boolean | null
  llm_reason: string | null
  created_at: string
  flags: Flag[]
}

export interface Trends {
  grade_distribution: Record<string, number>
  average_score: number | null
}

export interface Pattern {
  rule: string
  severity: string
  count: number
}

export const api = {
  repos: () => get<Repo[]>("/api/repos"),
  commits: (repo: string) => get<Commit[]>(`/api/repos/${repo}/commits`),
  trends: (repo: string) => get<Trends>(`/api/repos/${repo}/trends`),
  patterns: (repo: string) => get<Pattern[]>(`/api/repos/${repo}/patterns`),
}
