"use client"

import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { api, type Repo } from "@/api"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export function ReposPage() {
  const [repos, setRepos] = useState<Repo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.repos()
      .then(setRepos)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex flex-col gap-3 p-6">
      {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full" />)}
    </div>
  )

  if (error) return <p className="p-6 text-destructive">{error}</p>

  if (repos.length === 0) return (
    <div className="flex flex-col items-center justify-center gap-2 p-12 text-muted-foreground">
      <p className="text-lg font-medium">No repositories yet</p>
      <p className="text-sm">Push a commit with CommitSense CI enabled to see data here.</p>
    </div>
  )

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-2xl font-semibold">Repositories</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        {repos.map(repo => (
          <Link key={repo.id} to={`/repos/${encodeURIComponent(repo.name)}`}>
            <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
              <CardHeader>
                <CardTitle className="text-base">{repo.name}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  Since {new Date(repo.created_at).toLocaleDateString()}
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
