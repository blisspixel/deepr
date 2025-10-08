# Deepr Web Interface - Implementation Plan

**Goal:** Build a modern, React-based web interface that makes research operations effortless and cost-visible.

**Timeline:** Phased approach, MVP first, then iterative improvements.

**Philosophy:** Local-first deployment, progressively enhanced for cloud.

---

## Phase 1: Foundation (Week 1-2)

### Backend API Development

#### 1.1 Flask REST API (`deepr/api/`)

**Create API structure:**
```
deepr/api/
├── __init__.py
├── app.py                 # Flask app factory
├── routes/
│   ├── __init__.py
│   ├── jobs.py            # Job CRUD operations
│   ├── results.py         # Results retrieval
│   ├── cost.py            # Cost analytics
│   └── config.py          # Configuration management
├── middleware/
│   ├── cors.py            # CORS configuration
│   ├── auth.py            # API key validation
│   └── errors.py          # Error handling
├── schemas/
│   ├── job.py             # Pydantic schemas
│   ├── result.py
│   └── cost.py
└── websockets/
    └── events.py          # Socket.IO events
```

#### 1.2 API Endpoints

**Jobs:**
```python
POST   /api/v1/jobs              # Submit research job
GET    /api/v1/jobs              # List all jobs (paginated, filtered)
GET    /api/v1/jobs/:id          # Get job details
PATCH  /api/v1/jobs/:id          # Update job (cancel, priority)
DELETE /api/v1/jobs/:id          # Delete job
POST   /api/v1/jobs/batch        # Submit multiple jobs
POST   /api/v1/jobs/:id/cancel   # Cancel job
```

**Results:**
```python
GET    /api/v1/results           # List all results (paginated, filtered)
GET    /api/v1/results/:id       # Get result detail
GET    /api/v1/results/:id/download/:format  # Download (md, docx, pdf, json)
GET    /api/v1/results/search    # Full-text search
POST   /api/v1/results/:id/tags  # Add tags
DELETE /api/v1/results/:id/tags/:tag  # Remove tag
```

**Cost Analytics:**
```python
GET    /api/v1/cost/summary      # Daily/monthly summary
GET    /api/v1/cost/trends       # Spending trends (chart data)
GET    /api/v1/cost/breakdown    # By model, date, etc.
GET    /api/v1/cost/estimate     # Estimate cost for prompt
GET    /api/v1/cost/limits       # Current budget limits
PATCH  /api/v1/cost/limits       # Update budget limits
```

**Configuration:**
```python
GET    /api/v1/config            # Get all config
PATCH  /api/v1/config            # Update config
POST   /api/v1/config/test       # Test API connection
GET    /api/v1/config/status     # System status
```

**WebSocket Events:**
```python
# Server → Client
job.created         # New job submitted
job.updated         # Job status changed
job.completed       # Job finished
job.failed          # Job failed
cost.warning        # Approaching budget limit
cost.exceeded       # Budget exceeded

# Client → Server
subscribe.jobs      # Subscribe to job updates
unsubscribe.jobs    # Unsubscribe from updates
```

#### 1.3 API Implementation Tasks

- [ ] Create Flask app factory with CORS
- [ ] Implement job routes (CRUD)
- [ ] Integrate with existing queue system
- [ ] Implement result routes (retrieval, download)
- [ ] Integrate with existing storage backends
- [ ] Implement cost analytics routes
- [ ] Integrate with CostController
- [ ] Implement WebSocket server
- [ ] Add authentication middleware (optional for v1)
- [ ] Add request validation (Pydantic)
- [ ] Add error handling
- [ ] Add logging
- [ ] Write API tests
- [ ] Generate OpenAPI/Swagger docs

---

## Phase 2: Frontend Foundation (Week 2-3)

### 2.1 Project Setup

**Create React app:**
```bash
cd deepr/web
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

**Install core dependencies:**
```bash
npm install react-router-dom react-query axios socket.io-client
npm install zustand immer date-fns
npm install @tailwindcss/forms @tailwindcss/typography
npm install @radix-ui/react-dialog @radix-ui/react-dropdown-menu
npm install @radix-ui/react-tabs @radix-ui/react-toast
npm install recharts react-markdown react-syntax-highlighter
npm install -D @types/react @types/react-dom
npm install -D tailwindcss postcss autoprefixer
npm install -D prettier eslint-config-prettier
```

**Project structure:**
```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts          # Axios instance
│   │   ├── jobs.ts            # Job API calls
│   │   ├── results.ts         # Results API calls
│   │   ├── cost.ts            # Cost API calls
│   │   └── websocket.ts       # WebSocket client
│   ├── components/
│   │   ├── common/            # Reusable components
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Select.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Toast.tsx
│   │   │   └── ...
│   │   ├── jobs/              # Job-specific components
│   │   ├── results/           # Result-specific components
│   │   ├── cost/              # Cost-specific components
│   │   └── layout/            # Layout components
│   │       ├── Header.tsx
│   │       ├── Sidebar.tsx
│   │       └── Layout.tsx
│   ├── pages/
│   │   ├── Dashboard.tsx
│   │   ├── SubmitResearch.tsx
│   │   ├── JobsQueue.tsx
│   │   ├── ResultsLibrary.tsx
│   │   ├── ResultDetail.tsx
│   │   ├── CostAnalytics.tsx
│   │   └── Settings.tsx
│   ├── hooks/
│   │   ├── useJobs.ts
│   │   ├── useResults.ts
│   │   ├── useCost.ts
│   │   ├── useWebSocket.ts
│   │   └── useToast.ts
│   ├── store/
│   │   ├── index.ts           # Zustand store
│   │   ├── jobsSlice.ts
│   │   ├── resultsSlice.ts
│   │   ├── costSlice.ts
│   │   └── settingsSlice.ts
│   ├── types/
│   │   ├── job.ts
│   │   ├── result.ts
│   │   ├── cost.ts
│   │   └── api.ts
│   ├── utils/
│   │   ├── format.ts          # Format dates, currency, etc.
│   │   ├── validation.ts      # Form validation
│   │   └── constants.ts       # Constants
│   ├── styles/
│   │   └── globals.css        # Global styles + Tailwind
│   ├── App.tsx
│   ├── main.tsx
│   └── vite-env.d.ts
├── public/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
└── postcss.config.js
```

### 2.2 Design System Implementation

**Create component library:**
- [ ] Button variants (primary, secondary, ghost, danger)
- [ ] Input components (text, textarea, select, checkbox)
- [ ] Card component with variants
- [ ] Modal/Dialog component
- [ ] Toast notification system
- [ ] Progress indicators (bar, spinner, circular)
- [ ] Badge component (status, cost, tags)
- [ ] Table component (sortable, filterable)
- [ ] Empty states
- [ ] Loading skeletons

**Set up Tailwind config:**
```javascript
// tailwind.config.js
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#1a5490',
          50: '#eff6ff',
          100: '#dbeafe',
          // ... full scale
        },
        accent: {
          DEFAULT: '#22d3ee',
          // ... full scale
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
```

---

## Phase 3: Core Features (Week 3-5)

### 3.1 Dashboard Page

**Components to build:**
- [ ] QuickSubmitForm (prominent, above fold)
- [ ] CostEstimateCard (real-time updates)
- [ ] ActiveJobsList (live status updates)
- [ ] RecentResultsGrid (clickable cards)
- [ ] SpendingSummary (gauges, charts)
- [ ] QueueDepthIndicator

**Features:**
- [ ] Real-time cost estimation as user types
- [ ] WebSocket connection for live updates
- [ ] Budget warnings (visual indicators)
- [ ] Quick actions (view, cancel, download)
- [ ] Responsive grid layout

### 3.2 Submit Research Page

**Components to build:**
- [ ] PromptEditor (large textarea, markdown preview)
- [ ] ModelSelector (dropdown with descriptions)
- [ ] PrioritySelector
- [ ] WebSearchToggle
- [ ] AdvancedOptions (collapsible)
- [ ] CostEstimatePanel (prominent)
- [ ] TemplateLibrary (modal, searchable)
- [ ] DraftManager (save/load prompts)

**Features:**
- [ ] Real-time cost estimation
- [ ] Prompt validation (length, clarity)
- [ ] Template suggestions
- [ ] Auto-save drafts (localStorage)
- [ ] Budget warnings before submit
- [ ] Success/error feedback

### 3.3 Jobs Queue Page

**Components to build:**
- [ ] JobsFilterBar (status, model, date)
- [ ] JobsTable (sortable, paginated)
- [ ] JobCard (card view alternative)
- [ ] JobDetailModal (expand inline)
- [ ] BulkActionsBar (multi-select)

**Features:**
- [ ] Real-time status updates (WebSocket)
- [ ] Filter and search
- [ ] Sort by any column
- [ ] Pagination (infinite scroll or pages)
- [ ] View toggle (table vs cards)
- [ ] Bulk cancel/delete
- [ ] Inline job details
- [ ] Progress indicators

### 3.4 Results Library Page

**Components to build:**
- [ ] ResultsSearchBar (full-text search)
- [ ] ResultsFilterPanel (date, cost, model, tags)
- [ ] ResultsGrid (card-based)
- [ ] ResultCard (preview, actions)
- [ ] TagManager (add, remove, filter by tags)
- [ ] CollectionManager (organize results)

**Features:**
- [ ] Full-text search across all results
- [ ] Advanced filtering
- [ ] Tag management
- [ ] Collections/folders
- [ ] Sort options
- [ ] Grid/list view toggle
- [ ] Bulk actions

### 3.5 Result Detail Page

**Components to build:**
- [ ] ResultHeader (title, metadata, actions)
- [ ] TableOfContents (auto-generated from headings)
- [ ] MarkdownRenderer (with syntax highlighting)
- [ ] CitationLinks (clickable, formatted)
- [ ] DownloadMenu (multiple formats)
- [ ] ShareButton (generate link)
- [ ] TagEditor
- [ ] RelatedResults (similar results)

**Features:**
- [ ] Clean markdown rendering
- [ ] Syntax highlighting for code blocks
- [ ] Smooth scroll to TOC sections
- [ ] Copy sections with attribution
- [ ] Download in multiple formats
- [ ] Print-friendly view
- [ ] Share functionality
- [ ] Tag editing

### 3.6 Cost Analytics Page

**Components to build:**
- [ ] SpendingOverview (key metrics)
- [ ] SpendingTrendsChart (line chart, 30d)
- [ ] ModelBreakdownChart (pie chart)
- [ ] TopExpensiveJobs (bar chart)
- [ ] BudgetGauges (daily, monthly)
- [ ] CostAlerts (warnings, recommendations)
- [ ] ExportPanel (CSV, PDF)

**Features:**
- [ ] Interactive charts (Recharts)
- [ ] Date range selector
- [ ] Budget utilization tracking
- [ ] Anomaly detection
- [ ] Export capabilities
- [ ] Cost optimization tips

### 3.7 Settings Page

**Components to build:**
- [ ] APIConfigSection (provider, key, test)
- [ ] BudgetLimitsSection (per-job, daily, monthly)
- [ ] DefaultsSection (model, web search)
- [ ] PreferencesSection (theme, notifications)
- [ ] StorageSection (cache, export, delete)
- [ ] DangerZone (destructive actions)

**Features:**
- [ ] API key management (masked input)
- [ ] Test connection button
- [ ] Budget limit editing
- [ ] Theme switcher (light/dark/auto)
- [ ] Data export
- [ ] Clear cache
- [ ] Delete all (with confirmation)

---

## Phase 4: Polish & Enhancement (Week 5-6)

### 4.1 Responsive Design

**Tasks:**
- [ ] Mobile navigation (hamburger menu)
- [ ] Touch-friendly controls (44px min)
- [ ] Simplified mobile forms
- [ ] Swipe gestures
- [ ] Bottom navigation bar
- [ ] Test on real devices

### 4.2 Performance Optimization

**Tasks:**
- [ ] Code splitting per route
- [ ] Lazy loading components
- [ ] Image optimization
- [ ] Bundle size analysis
- [ ] Lighthouse audit (90+ score)
- [ ] Service worker (offline mode)

### 4.3 Accessibility

**Tasks:**
- [ ] Keyboard navigation
- [ ] ARIA labels
- [ ] Focus indicators
- [ ] Color contrast audit
- [ ] Screen reader testing
- [ ] Skip links

### 4.4 Testing

**Tasks:**
- [ ] Unit tests (Vitest)
- [ ] Component tests (Testing Library)
- [ ] Integration tests
- [ ] E2E tests (Playwright)
- [ ] Visual regression tests

---

## Phase 5: Deployment (Week 6)

### 5.1 Docker Configuration

**Create Dockerfiles:**

**Backend Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY deepr/ deepr/
COPY scripts/ scripts/

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "deepr.api.app:create_app()"]
```

**Frontend Dockerfile:**
```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

**Docker Compose:**
```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports:
      - "5000:5000"
    environment:
      - DEEPR_PROVIDER=${DEEPR_PROVIDER}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DEEPR_STORAGE=local
      - DEEPR_QUEUE=local
    volumes:
      - ./results:/app/results
      - ./queue:/app/queue
    restart: unless-stopped

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
    restart: unless-stopped

  worker:
    build:
      context: .
      dockerfile: Dockerfile.backend
    command: python -m deepr.worker
    environment:
      - DEEPR_PROVIDER=${DEEPR_PROVIDER}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DEEPR_STORAGE=local
      - DEEPR_QUEUE=local
    volumes:
      - ./results:/app/results
      - ./queue:/app/queue
    depends_on:
      - backend
    restart: unless-stopped
```

### 5.2 Documentation

**Tasks:**
- [ ] API documentation (OpenAPI/Swagger)
- [ ] User guide (screenshots)
- [ ] Installation guide
- [ ] Configuration guide
- [ ] Troubleshooting guide

---

## Implementation Checklist

### Backend API
- [ ] Flask app factory
- [ ] Jobs routes (CRUD)
- [ ] Results routes (retrieval, download)
- [ ] Cost analytics routes
- [ ] Configuration routes
- [ ] WebSocket server (Socket.IO)
- [ ] Error handling middleware
- [ ] CORS configuration
- [ ] Request validation (Pydantic)
- [ ] API tests
- [ ] OpenAPI/Swagger docs

### Frontend Core
- [ ] Vite + React + TypeScript setup
- [ ] Tailwind CSS configuration
- [ ] Component library (buttons, inputs, cards, etc.)
- [ ] Routing (React Router)
- [ ] State management (Zustand)
- [ ] API client (Axios + React Query)
- [ ] WebSocket client
- [ ] Toast notifications
- [ ] Loading states
- [ ] Error boundaries

### Pages & Features
- [ ] Dashboard (quick submit, stats, recent activity)
- [ ] Submit Research (form, cost estimate, validation)
- [ ] Jobs Queue (table, filters, real-time updates)
- [ ] Results Library (grid, search, filters, tags)
- [ ] Result Detail (markdown, TOC, download, share)
- [ ] Cost Analytics (charts, gauges, trends)
- [ ] Settings (API config, budgets, preferences)

### Polish
- [ ] Responsive design (mobile-friendly)
- [ ] Dark mode
- [ ] Keyboard shortcuts
- [ ] Accessibility (WCAG AA)
- [ ] Performance optimization
- [ ] Service worker (offline mode)
- [ ] Error handling
- [ ] Loading states

### Testing & Deployment
- [ ] Unit tests
- [ ] Integration tests
- [ ] E2E tests
- [ ] Lighthouse audit
- [ ] Docker configuration
- [ ] Docker Compose setup
- [ ] Nginx configuration
- [ ] Documentation

---

## Success Metrics

### User Experience
- Page load time < 2s
- Route transitions < 100ms
- Real-time updates < 500ms latency
- Mobile usability score > 90

### Accessibility
- WCAG 2.1 AA compliance
- Keyboard navigable
- Screen reader compatible

### Performance
- Lighthouse score > 90
- Bundle size < 500KB (gzipped)
- No memory leaks
- Smooth animations (60fps)

### User Adoption
- Time to first job < 2 minutes
- Error rate < 1%
- User satisfaction > 8/10

---

**Let's build something great.**
