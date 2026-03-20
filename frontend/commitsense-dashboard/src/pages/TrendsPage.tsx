"use client"

import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { api, type Trends } from "@/api"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts"

const chartConfig = {
  count: { label: "Commits", color: "hsl(var(--chart-1))" },
} satisfies ChartConfig

const GRADE_COLORS: Record<string, string> = {
  A: "hsl(var(--chart-1))",
  B: "hsl(var(--chart-2))",
  C: "hsl(var(--chart-3))",
  D: "hsl(var(--chart-4))",
}

export function TrendsPage() {
  const { repo } = useParams<{ repo: string }>()
  const repoId = Number(repo)
  const [trends, setTrends] = useState<Trends | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!repoId) return
    api.trends(repoId)
      .then(setTrends)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [repoId])

  const repoName = repo ?? ""

  if (loading) return (
    <div className="flex flex-col gap-3 p-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-64 w-full" />
    </div>
  )

  if (error) return <p className="p-6 text-destructive">{error}</p>
  if (!trends) return null

  const chartData = Object.entries(trends.grade_distribution)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([grade, count]) => ({ grade, count, fill: GRADE_COLORS[grade] ?? "hsl(var(--chart-5))" }))

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/" className="hover:underline">Repositories</Link>
        <span>/</span>
        <Link to={`/repos/${repo}`} className="hover:underline">{repoName}</Link>
        <span>/</span>
        <span className="text-foreground">Trends</span>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Average Score</CardTitle>
            <CardDescription>Lower is better (0 = Grade A)</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold">
              {trends.average_score !== null ? trends.average_score.toFixed(1) : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Total Commits</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold">
              {Object.values(trends.grade_distribution).reduce((a, b) => a + b, 0)}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Grade Distribution</CardTitle>
          <CardDescription>Commits by grade</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={chartConfig} className="h-64 w-full">
            <BarChart data={chartData}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="grade" />
              <YAxis allowDecimals={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="count" radius={4} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </div>
  )
}
