import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { ReposPage } from "@/pages/ReposPage"
import { CommitsPage } from "@/pages/CommitsPage"
import { TrendsPage } from "@/pages/TrendsPage"
import { PatternsPage } from "@/pages/PatternsPage"

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-svh bg-background">
        <header className="border-b px-6 py-3 flex items-center gap-3">
          <span className="font-semibold tracking-tight">CommitSense</span>
          <span className="text-muted-foreground text-sm">Dashboard</span>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<ReposPage />} />
            <Route path="/repos/:repo" element={<CommitsPage />} />
            <Route path="/repos/:repo/trends" element={<TrendsPage />} />
            <Route path="/repos/:repo/patterns" element={<PatternsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
