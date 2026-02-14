import { lazy } from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import AppShell from '@/components/layout/app-shell'
import { ErrorBoundary } from '@/components/error-boundary'

const Overview = lazy(() => import('@/pages/overview'))
const ResearchStudio = lazy(() => import('@/pages/research-studio'))
const ResearchLive = lazy(() => import('@/pages/research-live'))
const ResultsLibrary = lazy(() => import('@/pages/results-library'))
const ResultDetail = lazy(() => import('@/pages/result-detail'))
const ExpertHub = lazy(() => import('@/pages/expert-hub'))
const ExpertProfile = lazy(() => import('@/pages/expert-profile'))
const CostIntelligence = lazy(() => import('@/pages/cost-intelligence'))
const TraceExplorer = lazy(() => import('@/pages/trace-explorer'))
const Models = lazy(() => import('@/pages/benchmarks'))
const Help = lazy(() => import('@/pages/help'))
const Settings = lazy(() => import('@/pages/Settings'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000,
    },
  },
})

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
      <h1 className="text-4xl font-bold text-foreground">404</h1>
      <p className="text-sm text-muted-foreground">Page not found</p>
      <Link
        to="/"
        className="px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Back to home
      </Link>
    </div>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<AppShell />}>
              <Route index element={<Overview />} />
              <Route path="research" element={<ResearchStudio />} />
              <Route path="research/:id" element={<ResearchLive />} />
              <Route path="results" element={<ResultsLibrary />} />
              <Route path="results/:id" element={<ResultDetail />} />
              <Route path="experts" element={<ExpertHub />} />
              <Route path="experts/:name" element={<ExpertProfile />} />
              <Route path="costs" element={<CostIntelligence />} />
              <Route path="models" element={<Models />} />
              <Route path="traces/:id" element={<TraceExplorer />} />
              <Route path="help" element={<Help />} />
              <Route path="settings" element={<Settings />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
      <Toaster position="bottom-right" richColors closeButton />
    </QueryClientProvider>
  )
}

export default App
