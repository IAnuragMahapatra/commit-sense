"use client"

import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { api, type Pattern } from "@/api"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts"

const chartConfig = {
  count: { label: "Occurrences", color: "hsl(var(--chart-2))" },
} satisfies ChartConfig

const SEVERITY_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  info: "secondary",
  warning: "outline",
  critical: "destructive",
}

export function PatternsPage() {
  const { repo } = useParams<{ repo: string }>()
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!repo) return
    api.patterns(decodeURIComponent(repo))
      .then(setPatterns)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [repo])

  const repoName = decodeURIComponent(repo ?? "")

  if (loading) return (
    <div className="flex flex-col gap-3 p-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-64 w-full" />
    </div>
  )

  if (error) return <p className="p-6 text-destructive">{error}</p>

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/" className="hover:underline">Repositories</Link>
        <span>/</span>
        <Link to={`/repos/${repo}`} className="hover:underline">{repoName}</Link>
        <span>/</span>
        <span className="text-foreground">Patterns</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Top Rule Violations</CardTitle>
          <CardDescription>Most frequently triggered rules across all commits</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <BarChart data={patterns} layout="vertical">
              <CartesianGrid horizontal={false} />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="rule" width={160} tick={{ fontSize: 11 }} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="count" radius={4} fill="hsl(var(--chart-2))" />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-2">
        {patterns.map((p, i) => (
          <div key={i} className="flex items-center gap-3 text-sm">
            <span className="w-6 text-right font-mono text-muted-foreground">{p.count}×</span>
            <Badge variant={SEVERITY_VARIANTS[p.severity] ?? "secondary"}>{p.severity}</Badge>
            <span className="font-mono text-xs">{p.rule}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
