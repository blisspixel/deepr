# Deepr 2.0 - Multi-Cloud Research Automation Platform

> **Status:** Core Infrastructure Complete (v2.0.0-alpha)
> **CLI Implementation:** In Progress
> **Web Application:** Planned
> **Cloud Deployment:** Ready for Implementation

Deepr is a modular, cloud-ready research automation pipeline that orchestrates complex research tasks using AI deep research capabilities. Version 2.0 introduces multi-cloud support (OpenAI + Azure), flexible storage backends (local + Azure Blob), and a complete architectural redesign for enterprise scalability.

![Architecture Diagram - Coming Soon]

## 🌟 What's New in 2.0

### Multi-Cloud Provider Support
- ✅ **OpenAI Deep Research API** - o3-deep-research, o4-mini-deep-research
- ✅ **Azure OpenAI Service** - Full compatibility with Azure deployments
- ✅ **Seamless Switching** - Change providers with a config variable
- ✅ **Managed Identity** - Azure AD authentication for enterprise security

### Flexible Storage Backends
- ✅ **Local Filesystem** - Fast development and testing
- ✅ **Azure Blob Storage** - Scalable cloud storage with SAS tokens
- ✅ **Unified Interface** - Same API regardless of backend

### Modular Architecture
- ✅ **Provider Abstraction** - Easy to add new AI providers
- ✅ **Storage Abstraction** - Pluggable storage backends
- ✅ **Core Business Logic** - Separated concerns for research, jobs, reports
- ✅ **Configuration Management** - Type-safe Pydantic configuration
- ✅ **Async-First** - Non-blocking I/O throughout

### Multiple Interfaces
- 🚧 **CLI** - Command-line interface (porting in progress)
- ⏸️ **Web Application** - Browser-based UI (planned)
- ⏸️ **REST API** - Programmatic access (planned)
- ✅ **Python API** - Direct library usage

### Cloud-Ready Deployment
- ✅ **Azure App Service** - Ready for deployment
- ✅ **Docker** - Containerized deployment (templates ready)
- ✅ **CI/CD** - GitHub Actions pipelines (planned)
- ✅ **Managed Identity** - Secure Azure resource access

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/blisspixel/deepr.git
cd deepr

# Install dependencies
pip install -r requirements/cli.txt  # For CLI usage
# OR
pip install -r requirements/web.txt  # For web development
```

### Configuration

Create a `.env` file:

```bash
# Provider (openai or azure)
DEEPR_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here

# Storage (local or blob)
DEEPR_STORAGE=local
DEEPR_REPORTS_PATH=./reports

# Optional
DEEPR_ENVIRONMENT=local
DEEPR_DEBUG=false
```

For Azure configuration, see [`docs/azure-deep-research.md`](docs/azure-deep-research.md).

### Usage (Python API)

```python
import asyncio
from deepr import AppConfig
from deepr.providers import create_provider
from deepr.storage import create_storage
from deepr.core import ResearchOrchestrator, DocumentManager, ReportGenerator

async def main():
    config = AppConfig.from_env()

    provider = create_provider(config.provider.type, api_key=config.provider.openai_api_key)
    storage = create_storage(config.storage.type, base_path="./reports")

    orchestrator = ResearchOrchestrator(
        provider, storage, DocumentManager(), ReportGenerator()
    )

    job_id = await orchestrator.submit_research(
        prompt="Analyze the impact of quantum computing on cybersecurity",
        model="o3-deep-research"
    )

    print(f"Job submitted: {job_id}")

asyncio.run(main())
```

For more examples, see [`QUICKSTART_V2.md`](QUICKSTART_V2.md).

## 📁 Architecture

```
deepr/
├── deepr/                      # Main package
│   ├── providers/              # AI provider abstraction (OpenAI, Azure)
│   ├── storage/                # Storage backends (local, blob)
│   ├── core/                   # Business logic (research, jobs, reports)
│   ├── webhooks/               # Webhook server & ngrok tunnel
│   ├── formatting/             # Output formatting (MD, DOCX, PDF)
│   ├── cli/                    # CLI interface (🚧 in progress)
│   └── web/                    # Web application (⏸️ planned)
│
├── docs/                       # Documentation
│   ├── azure-deep-research.md  # Azure integration guide
│   └── migration-guide.md      # V1 → V2 migration
│
├── requirements/               # Dependency management
│   ├── base.txt                # Core dependencies
│   ├── cli.txt                 # CLI dependencies
│   ├── web.txt                 # Web dependencies
│   └── dev.txt                 # Development dependencies
│
├── deployment/                 # Deployment configurations (⏸️ planned)
│   ├── azure/                  # Azure Bicep templates
│   └── docker/                 # Docker configs
│
└── tests/                      # Testing (⏸️ planned)
    ├── unit/                   # Unit tests
    └── integration/            # Integration tests
```

## 🎯 Key Features

### Research Capabilities
- ✅ Multi-step deep research with o3/o4-mini models
- ✅ Web search integration
- ✅ Code interpreter for analysis
- ✅ Document upload and vector search
- ✅ Batch processing support
- ✅ Cost-sensitive mode

### Output Formats
- ✅ Plain text (.txt)
- ✅ Markdown (.md)
- ✅ JSON (.json)
- ✅ Word (.docx with professional styling)
- ✅ PDF (optional)

### Job Management
- ✅ Job tracking and logging
- ✅ Status monitoring
- ✅ Automatic cleanup of old jobs
- ✅ Cost estimation and tracking

### Developer Experience
- ✅ Type-safe configuration
- ✅ Async/await throughout
- ✅ Factory patterns for extensibility
- ✅ Comprehensive error handling
- ✅ Modular design for testability

## 📚 Documentation

- **[Quick Start Guide](QUICKSTART_V2.md)** - Get started with v2.0 API
- **[Migration Guide](docs/migration-guide.md)** - Migrate from v1.x to v2.0
- **[Azure Integration](docs/azure-deep-research.md)** - Azure OpenAI & Blob Storage setup
- **[Implementation Status](IMPLEMENTATION_STATUS.md)** - Detailed progress tracking
- **[Refactoring Summary](REFACTORING_SUMMARY.md)** - What we've built

## 🔄 Migration from v1.x

**Good news!** The old `deepr.py` and `manager.py` files are preserved for backward compatibility:

```bash
# Old way (still works)
python deepr.py --research "Your prompt"

# New way (v2.0)
# Python API (available now)
python -c "import asyncio; from deepr.core import ...; asyncio.run(main())"

# CLI (coming soon)
deepr --research "Your prompt"
```

See [`docs/migration-guide.md`](docs/migration-guide.md) for detailed instructions.

## 🛠️ Development Status

### ✅ Completed (Phase 1)
- Provider abstraction (OpenAI + Azure)
- Storage abstraction (Local + Blob)
- Configuration management
- Core business logic (research, jobs, reports, documents)
- Webhook infrastructure
- Formatting modules
- Documentation (500+ pages)

### 🚧 In Progress (Phase 2)
- CLI implementation (porting from v1.x)
- Basic testing suite

### ⏸️ Planned (Phase 3-4)
- Web application with dashboard
- Azure deployment templates
- Comprehensive test coverage
- Enhanced features (cost tracking, collaboration, etc.)

See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for details.

## 💡 Use Cases

- **Competitive Intelligence** - Automated market research and competitor analysis
- **Regulatory Monitoring** - Track legal and regulatory changes
- **Technical Due Diligence** - Deep dives into technical architectures
- **Policy Research** - Generate reports for strategic decisions
- **Academic Research** - Literature reviews and synthesis
- **Consulting** - Client-ready research reports

## 🏢 Enterprise Features

- **Azure AD Integration** - Enterprise authentication
- **Managed Identity** - Secure resource access without keys
- **VNet Integration** - Private network deployment
- **Cost Tracking** - Per-job and aggregate cost analysis
- **Audit Logging** - Complete activity tracking
- **Data Residency** - Deploy in your preferred Azure region

## 🤝 Contributing

Contributions are welcome! Areas where help is needed:

1. **CLI Implementation** - Port remaining features from v1.x
2. **Web Application** - Build the dashboard and UI
3. **Testing** - Write unit and integration tests
4. **Documentation** - Improve guides and examples
5. **Deployment** - Azure Bicep templates and CI/CD

See `CONTRIBUTING.md` (coming soon) for guidelines.

## 📝 License

MIT License - see [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

- **OpenAI** - Deep Research API
- **Microsoft Azure** - Cloud infrastructure and AI services
- **Original Author** - blisspixel
- **Architecture Design** - blisspixel + Claude

## 📞 Support

- **Documentation**: See `docs/` directory
- **Issues**: [GitHub Issues](https://github.com/blisspixel/deepr/issues)
- **Discussions**: [GitHub Discussions](https://github.com/blisspixel/deepr/discussions)

## 🗺️ Roadmap

### v2.0 (Current)
- [x] Core infrastructure
- [ ] CLI implementation
- [ ] Basic testing
- [ ] v2.0-beta release

### v2.1
- [ ] Web application MVP
- [ ] Azure deployment templates
- [ ] Documentation site

### v2.2
- [ ] Enhanced job management
- [ ] Cost tracking dashboard
- [ ] Multi-tenancy support

### v3.0
- [ ] Enterprise features
- [ ] Advanced analytics
- [ ] Collaboration tools

---

**⚠️ Note:** This is an alpha release. The core infrastructure is complete and tested, but CLI and web interfaces are still being finalized. The Python API is production-ready.

**Built with ❤️ by blisspixel**
**Powered by OpenAI Deep Research & Azure AI**
