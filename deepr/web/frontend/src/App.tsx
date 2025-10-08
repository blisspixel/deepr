import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import PrepResearch from './pages/PrepResearch'
import SubmitResearch from './pages/SubmitResearch'
import JobsQueue from './pages/JobsQueue'
import ResultsLibrary from './pages/ResultsLibrary'
import ResultDetail from './pages/ResultDetail'
import BatchStatus from './pages/BatchStatus'
import CostAnalytics from './pages/CostAnalytics'
import Settings from './pages/Settings'

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000, // 30 seconds
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="prep" element={<PrepResearch />} />
            <Route path="submit" element={<SubmitResearch />} />
            <Route path="jobs" element={<JobsQueue />} />
            <Route path="batch/:batchId" element={<BatchStatus />} />
            <Route path="results" element={<ResultsLibrary />} />
            <Route path="results/:id" element={<ResultDetail />} />
            <Route path="cost" element={<CostAnalytics />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
