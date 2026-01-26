# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 2.1.x   | Yes       |
| < 2.1   | No        |

---

## Security Features

Deepr implements multiple layers of security to protect users:

### Input Validation
- **Path Traversal Protection**: All file paths validated against base directories
- **Prompt Length Limits**: Maximum 50,000 characters to prevent cost-based DoS
- **File Upload Validation**: Size limits (100MB), extension whitelists, content validation
- **Expert Name Sanitization**: Prevents directory traversal via expert names

### Network Security
- **SSRF Protection**: Blocks requests to private IP ranges (localhost, 192.168.x.x, 10.x.x.x, etc.)
- **URL Validation**: Only HTTP/HTTPS allowed for web scraping
- **DNS Resolution Checks**: Validates resolved IPs before fetching

### API Key Protection
- **Environment Variables Only**: No hardcoded keys
- **Format Validation**: Provider-specific key format checking
- **Log Sanitization**: Automatic redaction of sensitive data in logs
- **Never Logged**: Keys never appear in error messages or debug output

### Budget Controls
- **Multi-Layer Limits**: Job-level, session-level, monthly, and global budgets
- **Cost Estimation**: Estimated costs shown before expensive operations
- **User Confirmation**: High-cost operations require explicit approval

### Subprocess Security
- **No Shell Injection**: All subprocess calls use list arguments (`shell=False`)
- **Command Whitelisting**: Only specific, validated commands executed

---

## Reporting a Vulnerability

**We take security seriously.** If you discover a security vulnerability, please report it responsibly.

### How to Report

**Email:** security@deepr.dev (or file a private security advisory on GitHub)

**Do NOT:**
- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before we've had a chance to address it

**Please Include:**
1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if you have one)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 1 week
- **Fix Timeline**: Depends on severity
  - Critical: 24-48 hours
  - High: 1 week
  - Medium: 2-4 weeks
  - Low: Next minor release

### Disclosure Policy

- We follow **coordinated disclosure**
- We'll work with you to understand and fix the issue
- We'll credit you in the security advisory (unless you prefer to remain anonymous)
- We'll notify users via:
  - GitHub Security Advisory
  - Release notes
  - README update

---

## Security Best Practices for Users

### API Key Management

**DO:**
- Use environment variables (`.env` file)
- Use pre-paid credits with auto-reload **OFF**
- Rotate keys regularly (every 90 days)
- Use separate keys for development vs. production
- Set `DEEPR_MAX_COST_PER_DAY` and `DEEPR_MAX_COST_PER_MONTH`

**DON'T:**
- Commit `.env` file to git
- Share API keys in chat/email
- Use production keys for testing
- Grant Deepr unnecessary permissions

### File Upload Safety

**DO:**
- Only upload files you trust
- Check file sizes before uploading
- Verify file extensions match content
- Use virus scanning on uploaded documents

**DON'T:**
- Upload executable files (.exe, .sh, .bat)
- Upload files from untrusted sources
- Upload sensitive documents without reviewing first

### Web Scraping Cautions

**DO:**
- Only scrape public websites
- Respect robots.txt
- Use reasonable rate limits
- Verify URLs before scraping

**DON'T:**
- Scrape internal/private URLs
- Attempt to bypass security controls
- Scrape sites without permission for commercial use

### Expert System Security

**DO:**
- Sanitize sensitive data before uploading to experts
- Use descriptive, simple expert names
- Monitor expert costs regularly
- Delete experts when no longer needed

**DON'T:**
- Upload confidential documents without review
- Share experts with sensitive data
- Use expert names with special characters or paths

### Budget Protection

**DO:**
- Start with small budgets (`deepr budget set 5`)
- Monitor with `deepr cost summary`
- Use `--limit` flag for individual operations
- Review estimates before confirming

**DON'T:**
- Set unlimited budgets
- Ignore cost warnings
- Skip confirmation prompts without reading
- Run autonomous learning without budget limits

---

## Known Security Considerations

### Local-First Design
- All processing happens locally
- No data sent to Deepr servers (we don't have any)
- Data only sent to chosen AI providers (OpenAI, Google, xAI, etc.)
- User responsible for provider trust decisions

### AI Provider Security
- Deepr uses third-party AI services
- Review provider privacy policies:
  - [OpenAI Privacy Policy](https://openai.com/policies/privacy-policy)
  - [Google AI Privacy](https://policies.google.com/privacy)
  - [xAI Terms](https://x.ai/legal/terms-of-service)
  - [Anthropic Privacy](https://www.anthropic.com/privacy)
- Prompts/documents sent to providers for processing
- Consider data sensitivity before using

### Web Scraping Risks
- Fetches external content
- Could encounter malicious websites
- Content parsing uses third-party libraries
- Selenium runs full browser (isolated, but uses resources)

### MCP Integration (Experimental)
- **Not yet production-tested**
- No authentication currently
- Designed for local use only
- **Do not expose MCP server to network**

---

## Security Audit

Last audit: **2026-01-21**

- [Full Audit Report](docs/SECURITY_AUDIT_2026-01-21.md)
- [Security Fixes Applied](docs/SECURITY_FIXES_2026-01-21.md)

**Overall Security Grade: B+**

---

## Compliance

### Data Privacy
- **GDPR Consideration**: User prompts may contain PII - consider before using EU citizen data
- **Data Retention**: All research stored locally - user controls retention
- **Data Deletion**: Simply delete files from `reports/` and `data/` directories
- **No Tracking**: Deepr does not collect telemetry or usage data

### PCI-DSS / HIPAA / SOC 2
- **Not Certified**: Deepr is not certified for regulated industries
- **Not Recommended**: For processing of regulated data (payment cards, healthcare, etc.)
- **User Responsibility**: Evaluate provider compliance if using for regulated data

---

## Security Roadmap

### v2.2 (Current Sprint)
- [DONE] Path traversal protection
- [DONE] SSRF protection for web scraping
- [DONE] File upload validation
- [DONE] Prompt length limits
- [WIP] Apply security fixes throughout codebase
- [WIP] Comprehensive security testing

### v2.3 (Next Release)
- Rate limiting per user/session
- Audit logging for security events
- Enhanced MCP authentication
- Dependency vulnerability scanning
- Automated security tests in CI/CD

### v2.4 (Future)
- Sandboxed file processing
- Content Security Policy for web UI
- Multi-user authentication
- Role-based access control
- SOC 2 Type II preparation

---

## Dependencies

Deepr uses dependencies from PyPI. We monitor for known vulnerabilities.

**Automatic Scanning:**
- Run `pip-audit` regularly
- Review GitHub Dependabot alerts
- Update dependencies monthly

**Manual Review:**
```bash
# Check for known vulnerabilities
pip install pip-audit
pip-audit

# Or use safety
pip install safety
safety check
```

---

## Contact

- **Security Issues**: security@deepr.dev (private)
- **General Issues**: [GitHub Issues](https://github.com/blisspixel/deepr/issues) (public)
- **Discussions**: [GitHub Discussions](https://github.com/blisspixel/deepr/discussions)

---

## Acknowledgments

We thank security researchers who responsibly disclose vulnerabilities:

- (List will be populated as researchers report issues)

---

**Last Updated:** 2026-01-21
**Next Review:** After v2.2 release
