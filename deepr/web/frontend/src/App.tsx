import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { Loader2 } from 'lucide-react'
import AppShell from '@/components/layout/app-shell'

const Overview = lazy(() => import('@/pages/overview'))
const ResearchStudio = lazy(() => import('@/pages/research-studio'))
const ResearchLive = lazy(() => import('@/pages/research-live'))
const ResultsLibrary = lazy(() => import('@/pages/results-library'))
const ResultDetail = lazy(() => import('@/pages/result-detail'))
const ExpertHub = lazy(() => import('@/pages/expert-hub'))
const ExpertProfile = lazy(() => import('@/pages/expert-profile'))
const CostIntelligence = lazy(() => import('@/pages/cost-intelligence'))
const TraceExplorer = lazy(() => import('@/pages/trace-explorer'))
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

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-[60vh]">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
    </div>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<PageLoader />}>
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
              <Route path="traces/:id" element={<TraceExplorer />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
      <Toaster position="bottom-right" richColors closeButton />
    </QueryClientProvider>
  )
}

export default App
