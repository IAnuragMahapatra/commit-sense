"use client"

import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { api, type Commit } from "@/api"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"

const GRADE_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  A: "default",
  B: "secondary",
  C: "outline",
  D: "destructive",
}

const SEVERITY_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  info: "secondary",
  warning: "outline",
  critical: "destructive",
}

export function CommitsPage() {
  const { repo } = useParams<{ repo: string }>()
  const repoId = Number(repo)
  const [commits, setCommits] = useState<Commit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    if (!repoId) return
    api.commits(repoId)
      .then(setCommits)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [repoId])

  if (loading) return (
    <div className="flex flex-col gap-3 p-6">
      {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12 w-full" />)}
    </div>
  )

  if (error) return <p className="p-6 text-destructive">{error}</p>

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/" className="text-sm text-muted-foreground hover:underline">Repositories</Link>
          <span className="mx-2 text-muted-foreground">/</span>
          <span className="text-sm font-medium">{repo}</span>
        </div>
        <div className="flex gap-2">
          <Link to={`/repos/${repo}/trends`} className="text-sm text-muted-foreground hover:underline">Trends</Link>
          <span className="text-muted-foreground">·</span>
          <Link to={`/repos/${repo}/patterns`} className="text-sm text-muted-foreground hover:underline">Patterns</Link>
        </div>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-20">Grade</TableHead>
            <TableHead className="w-16">Score</TableHead>
            <TableHead>Message</TableHead>
            <TableHead className="w-16">SHA</TableHead>
            <TableHead className="w-24">LLM</TableHead>
            <TableHead className="w-28">Date</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {commits.map(c => (
            <>
              <TableRow
                key={c.sha}
                className="cursor-pointer"
                onClick={() => setExpanded(expanded === c.sha ? null : c.sha)}
              >
                <TableCell>
                  {c.grade && (
                    <Badge variant={GRADE_VARIANTS[c.grade] ?? "outline"}>{c.grade}</Badge>
                  )}
                </TableCell>
                <TableCell className="font-mono text-sm">{c.score ?? "—"}</TableCell>
                <TableCell className="max-w-xs truncate">
                  {c.rewritten_message ? (
                    <span title={`Original: ${c.original_message ?? ""}`}>
                      {c.rewritten_message} <span className="text-xs text-muted-foreground">(amended)</span>
                    </span>
                  ) : c.original_message}
                </TableCell>
                <TableCell className="font-mono text-xs">{c.sha.slice(0, 7)}</TableCell>
                <TableCell>
                  {c.llm_aligned === null ? "—" :
                    c.llm_aligned ? "✅" : "❌"}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(c.created_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
              {expanded === c.sha && c.flags.length > 0 && (
                <TableRow key={`${c.sha}-flags`}>
                  <TableCell colSpan={6} className="bg-muted/30">
                    <div className="flex flex-col gap-1 py-1">
                      {c.flags.map((f, i) => (
                        <div key={i} className="flex items-start gap-2 text-sm">
                          <Badge variant={SEVERITY_VARIANTS[f.severity] ?? "secondary"} className="shrink-0">
                            {f.severity}
                          </Badge>
                          <span className="font-mono text-xs text-muted-foreground">{f.rule}</span>
                          <span className="text-xs">{f.detail}</span>
                        </div>
                      ))}
                      {c.llm_reason && (
                        <p className="text-xs text-muted-foreground mt-1">LLM: {c.llm_reason}</p>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
