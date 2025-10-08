# React Frontend Implementation - Complete

## Overview

Complete React-based web interface for Deepr with modern UI/UX, real-time updates, and comprehensive cost analytics.

## Technology Stack

- **React 18** - Latest React with hooks and concurrent features
- **TypeScript** - Type-safe development
- **Vite** - Fast development and optimized builds
- **React Router** - Client-side routing
- **React Query** - Data fetching, caching, and real-time updates
- **Socket.IO Client** - WebSocket connections for live updates
- **Tailwind CSS** - Utility-first styling with custom Deepr theme
- **Recharts** - Data visualization for cost analytics
- **React Markdown** - Markdown rendering for research results
- **Axios** - HTTP client with interceptors

## Project Structure

```
deepr/web/frontend/
├── src/
│   ├── api/                  # API client layer
│   │   ├── client.ts         # Axios instance with interceptors
│   │   ├── websocket.ts      # Socket.IO client wrapper
│   │   ├── jobs.ts           # Job management API
│   │   ├── results.ts        # Results retrieval API
│   │   ├── cost.ts           # Cost analytics API
│   │   └── config.ts         # Configuration API
│   ├── components/
│   │   ├── common/           # Reusable UI components
│   │   │   ├── Button.tsx    # Primary, secondary, ghost, danger variants
│   │   │   ├── Card.tsx      # Card with Header, Body, Footer
│   │   │   ├── Input.tsx     # Text input with label, error, helper text
│   │   │   ├── TextArea.tsx  # Multi-line text input
│   │   │   └── Select.tsx    # Dropdown selector
│   │   └── layout/
│   │       └── Layout.tsx    # Main layout with nav and WebSocket setup
│   ├── pages/                # Route components
│   │   ├── Dashboard.tsx     # Quick submit + stats + recent jobs
│   │   ├── SubmitResearch.tsx # Full research submission form
│   │   ├── JobsQueue.tsx     # Jobs table/cards with filters
│   │   ├── ResultsLibrary.tsx # Grid/list view of completed research
│   │   ├── ResultDetail.tsx  # Full result viewer with export
│   │   ├── CostAnalytics.tsx # Charts and spending dashboard
│   │   └── Settings.tsx      # Configuration with tabbed interface
│   ├── types/
│   │   └── index.ts          # TypeScript interfaces
│   ├── App.tsx               # Router setup with React Query provider
│   └── main.tsx              # Entry point
├── package.json              # Dependencies
├── tsconfig.json             # TypeScript configuration
├── vite.config.ts            # Vite bundler config
└── tailwind.config.js        # Tailwind theme with Deepr colors
```

## Features Implemented

### 1. Dashboard (`/`)
- **Quick Submit Form** - Submit research without navigating away
- **Real-time Cost Estimation** - Calculates cost as you type (triggers after 10 chars)
- **Stats Cards** - Active jobs, daily spending, monthly spending with progress bars
- **Recent Jobs Feed** - Last 5 jobs with live status updates (polls every 5s)
- **Model Selection** - Choose between o4-mini or o3

### 2. Submit Research (`/submit`)
- **Large Prompt Input** - 8-row textarea with character counter
- **Advanced Options Grid**:
  - Model selector (o4-mini / o3)
  - Priority selector (High / Normal / Low)
  - Web search toggle checkbox
- **Real-time Cost Panel** - Blue card showing:
  - Expected cost (bold)
  - Min-max range
  - Budget validation with warnings
  - Blocks submission if over budget
- **Tips Section** - Best practices for writing prompts
- **Form Validation** - Prevents empty submissions

### 3. Jobs Queue (`/jobs`)
- **Dual View Modes** - Table or cards view toggle
- **Advanced Filters**:
  - Status (all, pending, in_progress, completed, failed)
  - Model (all models plus specific model filter)
- **Bulk Operations**:
  - Select all checkbox
  - Individual job selection
  - Bulk cancel with confirmation
- **Real-time Updates** - WebSocket events update job status instantly
- **Status Badges** - Color-coded (green=completed, blue=in_progress, red=failed, gray=pending)
- **Polling Fallback** - Refetches every 5 seconds
- **Actions**:
  - Cancel button for in_progress jobs
  - View button for completed jobs

### 4. Results Library (`/results`)
- **Grid/List Toggle** - Adaptive layouts for different browsing styles
- **Full-text Search** - Search across prompts and content
- **Sort Options** - By date, cost, or model
- **Result Cards** (Grid):
  - Truncated prompt and content preview
  - Model, cost, completion date
  - Citation count badge
  - Click to view full result
- **Result Rows** (List):
  - More content preview
  - Quick metadata display
  - View button
- **Stats Footer** - Total results, total cost, total citations, avg content length
- **Empty State** - Helpful message with call-to-action
- **Responsive** - 3 columns on desktop, 2 on tablet, 1 on mobile

### 5. Result Detail (`/results/:id`)
- **Navigation** - Back to library button
- **Header** - Full prompt, job ID, model, cost, timestamp
- **View Modes**:
  - Formatted (rendered Markdown with prose styling)
  - Raw Markdown (monospace pre-wrap)
- **Export Options**:
  - Markdown (.md)
  - PDF (.pdf)
  - JSON (.json)
  - Downloads automatically via blob URLs
- **Citations Panel** - If present:
  - Numbered list [1], [2], etc.
  - Title, URL, snippet
  - Open in new tab button
- **Metadata Card** - Complete job details in 2-column grid
- **Error Handling** - 404 page if result not found

### 6. Cost Analytics (`/cost`)
- **Summary Cards**:
  - Today's spending with progress bar (green/yellow/red)
  - Monthly spending with progress bar
  - Total spending all-time
  - Average cost per job
- **Time Range Filter** - 7 days, 30 days, 90 days
- **Spending Over Time** - Line chart showing daily costs
- **Cost Breakdown Charts**:
  - Pie chart by model with legend
  - Bar chart jobs by status
- **Budget Alerts** - Yellow warning card if >80% utilization
- **Responsive Charts** - Recharts with dark mode support

### 7. Settings (`/settings`)
- **Tabbed Interface**:
  1. **General** - Default model, priority, web search toggle
  2. **API Keys** - OpenAI key, Azure key, Azure endpoint (password fields)
  3. **Cost Limits** - Daily limit, monthly limit, max concurrent jobs (number inputs)
  4. **Storage** - Local vs Azure, connection string
- **Form State Management** - useState with controlled inputs
- **Save Buttons** - Per-tab with loading states
- **Success/Error Feedback** - Green/red cards after mutation
- **Input Validation** - Type-safe number inputs with min/max
- **Helper Text** - Context-aware guidance for each field

## Real-time Updates

### Polling Strategy (Primary)
```typescript
useQuery({
  queryKey: ['jobs', 'list'],
  queryFn: () => jobsApi.list(),
  refetchInterval: 5000, // Poll every 5 seconds
})
```

Used for:
- Jobs list
- Cost summary
- Recent jobs on dashboard

### WebSocket Updates (Secondary)
```typescript
useEffect(() => {
  const handleJobUpdate = (job: Job) => {
    queryClient.setQueryData(['jobs', 'list'], (old: any) => {
      // Update job in cache
    })
  }

  wsClient.on('job_updated', handleJobUpdate)
  wsClient.subscribeToJobs()

  return () => wsClient.off('job_updated', handleJobUpdate)
}, [])
```

Events:
- `job_created` - New job added to queue
- `job_updated` - Status or metadata changed
- `job_completed` - Job finished successfully
- `job_failed` - Job encountered error

## Styling & Theming

### Deepr Color Palette
```javascript
colors: {
  primary: {
    DEFAULT: '#1a5490',  // Deep Blue
    600: '#1a5490',
    700: '#1e40af',
  },
  accent: {
    DEFAULT: '#22d3ee',  // Electric Cyan
  },
}
```

### Dark Mode
- All components support dark mode via Tailwind's `dark:` prefix
- Automatic detection via system preferences
- Consistent contrast ratios for accessibility

### Component Patterns
- **Cards** - White/gray-800 background with border
- **Buttons** - Primary (blue), secondary (gray), ghost (transparent), danger (red)
- **Inputs** - Consistent border, focus ring, error states
- **Status Badges** - Rounded pills with semantic colors

## API Integration

### Base Configuration
```typescript
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:5000/api/v1',
  timeout: 30000,
})
```

### Error Handling
```typescript
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.error || error.message
    console.error('API Error:', message)
    return Promise.reject(error)
  }
)
```

### Type Safety
All API responses and requests use TypeScript interfaces from `types/index.ts`:
- `Job`, `Result`, `CostEstimate`, `CostSummary`, etc.
- Compile-time checking for API contracts
- IntelliSense support in editors

## Performance Optimizations

1. **React Query Caching** - Reduces redundant API calls
   - 30-second stale time
   - Background refetching
   - Query invalidation on mutations

2. **Code Splitting** - Vite automatically splits routes
   - Lazy loading per page
   - Smaller initial bundle size

3. **Debounced Search** - Cost estimation triggers after 10 characters
   - Prevents API spam while typing

4. **Polling Intervals** - Balanced for freshness vs load
   - Jobs: 5 seconds
   - Cost summary: 10 seconds
   - Results: 10 seconds

5. **WebSocket Subscriptions** - Targeted updates
   - Subscribe to specific job rooms
   - Reduces unnecessary event processing

## Responsive Design

### Breakpoints
- **Mobile**: 320-767px (1 column grids, stacked navigation)
- **Tablet**: 768-1279px (2 column grids, compact nav)
- **Desktop**: 1280px+ (3 column grids, full navigation)

### Mobile Optimizations
- Hamburger menu (planned for mobile nav)
- Card view default on small screens
- Touch-friendly buttons (min 44x44px)
- Simplified tables with horizontal scroll

## Environment Variables

```env
VITE_API_URL=http://localhost:5000/api/v1
VITE_WS_URL=http://localhost:5000
```

Override in `.env.local` for development or `.env.production` for builds.

## Build & Deploy

### Development
```bash
npm install
npm run dev
# Opens http://localhost:5173
```

### Production Build
```bash
npm run build
# Creates optimized bundle in dist/
```

### Preview
```bash
npm run preview
# Test production build locally
```

## Testing Checklist

- [ ] All routes navigate correctly
- [ ] WebSocket connects and receives events
- [ ] Cost estimation updates in real-time
- [ ] Job submission works with validation
- [ ] Filters and search function correctly
- [ ] Export buttons download files
- [ ] Settings save and persist
- [ ] Dark mode toggles properly
- [ ] Responsive on mobile, tablet, desktop
- [ ] Error states display correctly
- [ ] Loading states show during API calls

## Future Enhancements

### Research Planner (Next Priority)
User request: "Prep" feature to decompose high-level scenarios into multiple research tasks.

**Concept:**
1. User submits scenario: "Meeting with Company X about Topic Y tomorrow"
2. GPT-4o or o1 analyzes and plans multi-angle research strategy
3. System creates N jobs automatically:
   - Company background research
   - Industry analysis
   - Technical deep dive on relevant technology
   - Competitor landscape
   - Use case examples
4. User configures max sub-tasks (e.g., 3-5 reports)
5. All jobs added to queue with linked "batch ID"
6. Dashboard shows batch progress

**Implementation Plan:**
- Add `/plan` route with planner interface
- New API endpoint: `POST /jobs/plan`
  - Input: scenario, max_tasks, model
  - Returns: array of planned prompts
- User reviews and approves before submission
- Batch tracking in Jobs Queue
- Aggregate view in Results Library for batches

### Other Ideas
- [ ] Job templates library (save and reuse prompts)
- [ ] Result comparison view (side-by-side)
- [ ] Export to Notion, Google Docs, etc.
- [ ] Collaborative features (sharing, comments)
- [ ] Mobile app (React Native)
- [ ] Notifications (email, Slack, Discord)
- [ ] Advanced analytics (trends, predictions)
- [ ] Custom model fine-tuning interface

## Deployment Architecture

### Local-First (Priority 1)
```
User Workstation (Linux/Mac/Windows)
├── deepr CLI
├── Flask API (localhost:5000)
├── Polling Worker (background process)
├── React App (built to static HTML/JS)
└── SQLite database
```

Serve React app via Flask static routes or standalone HTTP server.

### Containerized (Priority 2)
```
Docker Compose
├── api (Flask + SocketIO)
├── worker (Polling process)
├── web (Nginx serving React build)
└── volumes (SQLite persistence)
```

Single `docker-compose up` command.

### Cloud (Priority 3)
```
Azure
├── App Service (API)
├── Static Web Apps (React)
├── Azure Functions (Worker)
└── Table Storage + Blobs (Data)
```

For teams needing shared access.

## Documentation

- **API Docs**: `docs/web/API_DOCUMENTATION.md`
- **UI/UX Review**: `docs/web/UI_UX_REVIEW.md`
- **Implementation Plan**: `docs/web/IMPLEMENTATION_PLAN.md`
- **Backend Summary**: `docs/web/IMPLEMENTATION_SUMMARY.md`
- **Webhook Strategy**: `docs/WEBHOOK_STRATEGY.md`

## Support

Built with React 18, TypeScript, and modern web standards. Tested on:
- Chrome 120+
- Firefox 121+
- Safari 17+
- Edge 120+

For issues or questions, see the main README.
