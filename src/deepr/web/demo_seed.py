"""Static seed content for the web demo mode.

Report bodies and sample job rows for /api/demo/load. Data only - the route
logic (namespacing, scoped cleanup) lives in app.py. Extracted so the demo
fixture text does not count against app.py's size budget.
"""

DEMO_REPORTS = [
    # 0: Quantum error correction
    "# Quantum Error Correction: 2025-2026 Breakthroughs\n\n"
    "## Executive Summary\n\n"
    "The past 18 months have seen transformative advances in quantum error correction (QEC), "
    "bringing fault-tolerant quantum computing meaningfully closer to reality. Google's Willow "
    "chip demonstrated below-threshold surface code performance, while Microsoft's topological "
    "qubits achieved their first logical operations. This report surveys the key breakthroughs, "
    "compares approaches, and assesses the timeline to practical fault tolerance.\n\n"
    "## Key Findings\n\n"
    "### Surface Codes Hit Inflection Point\n\n"
    "Google's 105-qubit Willow processor achieved a landmark result: increasing code distance "
    "from 3 to 7 reduced logical error rates exponentially, falling below the critical threshold "
    "for the first time. At distance-7, the logical error rate reached 1 in 10^7 per cycle, "
    "roughly a 10x improvement per additional distance step. IBM followed with similar results "
    "on their Heron architecture, demonstrating that surface code scaling is reproducible across "
    "hardware platforms.\n\n"
    "### Topological Approaches Mature\n\n"
    "Microsoft announced the first topological qubit operations using Majorana-based hardware, "
    "achieving a two-qubit gate fidelity of 99.2%. While still behind superconducting surface "
    "codes in absolute performance, the inherent noise protection of topological qubits means "
    "fewer physical qubits per logical qubit - potentially 10-100x fewer at scale. Academic groups "
    "at Delft and Copenhagen independently verified the Majorana signatures, strengthening "
    "confidence in the approach.\n\n"
    "### Hybrid and Novel Codes\n\n"
    "Several groups explored LDPC (low-density parity-check) codes that promise better encoding "
    "rates than surface codes. Quantinuum demonstrated a [[144,12,12]] bivariate bicycle code "
    "on trapped-ion hardware, encoding 12 logical qubits with a code distance of 12 - a "
    "significant step toward more efficient quantum memory. Additionally, bosonic codes using "
    "cat states in superconducting cavities showed error rates compatible with concatenation "
    "into surface codes, offering a promising hybrid path.\n\n"
    "## Implications\n\n"
    "These results collectively suggest that a 1,000-logical-qubit machine - sufficient for "
    "meaningful quantum chemistry and optimization - could be achievable within 5-8 years, "
    "assuming current scaling trends hold. The primary bottleneck has shifted from physics to "
    "engineering: fabrication yield, cryogenic wiring, and classical decoding throughput.\n\n"
    "## References\n\n"
    "- [Google Quantum AI - Willow Results](https://blog.google/technology/research/google-willow-quantum-chip/)\n"
    "- [Microsoft Topological Qubits](https://news.microsoft.com/source/features/innovation/microsofts-majorana-1-chip/)\n"
    "- [Quantinuum LDPC Demonstration](https://www.quantinuum.com/blog/logical-qubits)\n"
    "- [Nature - Surface Code Threshold](https://www.nature.com/articles/s41586-024-08449-y)\n",
    # 1: Carbon border adjustment
    "# Carbon Border Adjustment Mechanisms: Cross-Regional Economic Impact\n\n"
    "## Executive Summary\n\n"
    "Carbon border adjustment mechanisms (CBAMs) are reshaping global trade flows as the EU's "
    "mechanism enters its definitive phase and the US considers parallel legislation. This "
    "analysis examines the economic impact across major trading blocs, with particular attention "
    "to effects on developing nations and potential WTO compatibility challenges.\n\n"
    "## Key Findings\n\n"
    "### EU CBAM Implementation\n\n"
    "The EU's CBAM, which began its transitional reporting phase in October 2023 and moves to "
    "full financial adjustment in 2026, covers cement, iron and steel, aluminium, fertilizers, "
    "electricity, and hydrogen. Early data shows a 12-18% reduction in carbon-intensive imports "
    "from non-EU countries, with significant trade diversion toward suppliers in countries with "
    "comparable carbon pricing. Turkey and Ukraine have been most affected, while North African "
    "producers face the steepest compliance costs relative to GDP.\n\n"
    "### US Policy Landscape\n\n"
    "The US has not enacted a federal carbon border tax, but the PROVE IT Act (introduced 2024) "
    "and the Foreign Pollution Fee Act represent bipartisan momentum. Analysis suggests a US "
    "CBAM modeled on the EU approach would generate $6-10 billion annually, primarily from "
    "imports of steel, aluminum, and cement from China and India. However, the absence of a "
    "domestic carbon price complicates WTO justification.\n\n"
    "### Developing Nation Impact\n\n"
    "For many developing economies, CBAMs represent a significant trade barrier. Our modeling "
    "shows GDP impacts ranging from -0.3% to -1.2% for carbon-intensive exporters like India, "
    "Vietnam, and Egypt. However, nations investing in renewable energy infrastructure - "
    "particularly Morocco, Chile, and Kenya - are positioning themselves as preferred suppliers. "
    "The key policy question is whether CBAM revenue should fund climate adaptation in affected "
    "developing countries.\n\n"
    "## Trade Flow Analysis\n\n"
    "Using a computable general equilibrium model, we find that global trade in CBAM-covered "
    "sectors shifts by approximately $47 billion annually under full implementation. Winners "
    "include domestic EU producers and low-carbon exporters; losers are concentrated in "
    "fossil-fuel-dependent economies. Carbon leakage risk drops by 30-40% compared to "
    "unilateral carbon pricing without border adjustment.\n\n"
    "## References\n\n"
    "- [European Commission - CBAM Overview](https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism_en)\n"
    "- [World Bank - Carbon Pricing Dashboard](https://carbonpricingdashboard.worldbank.org/)\n"
    "- [IMF Working Paper - Border Carbon Adjustments](https://www.imf.org/en/Publications/WP)\n"
    "- [UNCTAD - Trade and Climate Change](https://unctad.org/topic/trade-and-environment)\n",
    # 2: React Server Components vs SSR
    "# React Server Components vs Traditional SSR\n\n"
    "## Executive Summary\n\n"
    "React Server Components (RSC) represent a fundamental shift in how React applications "
    "handle server-side rendering. Unlike traditional SSR which renders the full component tree "
    "on the server and hydrates on the client, RSC allows individual components to execute "
    "exclusively on the server while seamlessly integrating with interactive client components. "
    "This report benchmarks performance, evaluates developer experience, and provides migration "
    "guidance for enterprise teams.\n\n"
    "## Key Findings\n\n"
    "### Performance Benchmarks\n\n"
    "In our testing across three representative enterprise applications (e-commerce, dashboard, "
    "content site), RSC delivered:\n\n"
    "- **35-45% smaller JavaScript bundles** due to server-only dependencies never reaching the client\n"
    "- **20-30% faster Time to Interactive (TTI)** by eliminating hydration for static content\n"
    "- **15-25% reduction in API calls** as data fetching moves to the server component layer\n\n"
    "Traditional SSR with streaming (React 18) narrows the gap on initial load metrics but "
    "cannot match RSC's bundle size advantages for content-heavy pages.\n\n"
    "### Developer Experience\n\n"
    "RSC introduces a new mental model: the 'use client' directive creates a clear boundary "
    "between server and client code. In our developer survey (n=128 enterprise developers), "
    "67% reported the boundary confusing initially but valuable once understood. The primary "
    "friction points are: inability to use hooks in server components, serialization constraints "
    "on props passed across the boundary, and debugging complexity with mixed execution environments.\n\n"
    "### Migration Strategy\n\n"
    "For enterprise applications, we recommend an incremental approach:\n\n"
    "1. Start with leaf components that fetch data (tables, lists, detail views)\n"
    "2. Convert layout and navigation components that don't need interactivity\n"
    "3. Keep form components, modals, and stateful widgets as client components\n"
    "4. Adopt Next.js App Router as the framework layer - it provides the most mature RSC "
    "implementation with caching, routing, and streaming support\n\n"
    "## References\n\n"
    "- [React - Server Components RFC](https://react.dev/blog/2023/03/22/react-labs-what-we-have-been-working-on-march-2023)\n"
    "- [Next.js - App Router Documentation](https://nextjs.org/docs/app)\n"
    "- [Vercel - RSC Performance Study](https://vercel.com/blog)\n",
    # 3: Autonomous vehicle regulation
    "# Autonomous Vehicle Regulation: Global Status Report (2026)\n\n"
    "## Executive Summary\n\n"
    "Autonomous vehicle (AV) regulation has entered a critical phase as Level 4 commercial "
    "deployments expand globally. This report surveys the liability frameworks, safety standards, "
    "and insurance models emerging across major jurisdictions, highlighting both convergence and "
    "divergence in regulatory approaches.\n\n"
    "## Key Findings\n\n"
    "### Liability Frameworks\n\n"
    "Three distinct liability models have emerged. The US follows a manufacturer-liability "
    "approach where the AV developer assumes liability for crashes in autonomous mode, with "
    "state-level variations. The EU's revised Product Liability Directive (2024) applies strict "
    "liability to AI systems including AVs, with a rebuttable presumption of defect when AI "
    "causes harm. China's approach assigns liability to the vehicle operator by default, with "
    "provisions for manufacturer liability only when defects are proven - creating a more "
    "conservative framework.\n\n"
    "### Safety Standards\n\n"
    "UNECE WP.29 adopted the Automated Lane Keeping System (ALKS) regulation, now recognized "
    "by 47 countries. The US NHTSA issued its final AV safety framework (AVSSF) in 2025, "
    "establishing minimum performance requirements for perception, planning, and fallback "
    "systems. Notably, these standards require a minimum of 10 million miles of validated "
    "testing data and 1,000 hours of scenario-based testing covering 500+ edge cases.\n\n"
    "### Insurance Models\n\n"
    "The insurance industry has developed AV-specific products: single-vehicle policies covering "
    "both conventional and autonomous modes (pioneered by Allianz), fleet-level insurance for "
    "robotaxi operators (led by Munich Re), and parametric policies triggered by specific AV "
    "system failures. Premiums for Level 4 fleets are currently 40-60% higher than comparable "
    "human-driven fleets, but insurers project parity by 2028 as actuarial data accumulates.\n\n"
    "## Outlook\n\n"
    "Regulatory harmonization remains the key challenge. While technical standards are converging "
    "through UNECE, liability frameworks diverge significantly. Companies operating across "
    "jurisdictions face compliance costs of $5-15 million annually for regulatory adaptation.\n\n"
    "## References\n\n"
    "- [UNECE - Automated Driving Regulations](https://unece.org/transport/vehicle-regulations)\n"
    "- [NHTSA - AV Safety Framework](https://www.nhtsa.gov/technology-innovation/automated-vehicles-safety)\n"
    "- [European Commission - AI Liability Directive](https://commission.europa.eu/legal-notice_en)\n"
    "- [McKinsey - AV Insurance Market](https://www.mckinsey.com/industries/automotive-and-assembly)\n"
    "- [SAE International - J3016 Automation Levels](https://www.sae.org/standards/content/j3016_202104/)\n",
    # 4: LLM alignment techniques
    "# Large Language Model Alignment Techniques: A Systematic Review\n\n"
    "## Executive Summary\n\n"
    "Aligning large language models with human values and intentions remains one of the most "
    "critical challenges in AI development. This review compares the major alignment approaches - "
    "RLHF, DPO, Constitutional AI, and newer methods - evaluating their effectiveness, "
    "scalability, and limitations based on published research through early 2026.\n\n"
    "## Key Findings\n\n"
    "### RLHF (Reinforcement Learning from Human Feedback)\n\n"
    "RLHF remains the most widely deployed alignment technique. The standard pipeline - "
    "supervised fine-tuning, reward model training, and PPO optimization - has been refined "
    "significantly since its introduction. Key improvements include reward model ensembles to "
    "reduce reward hacking, KL-penalty scheduling for training stability, and process-based "
    "reward models that evaluate reasoning steps rather than final outputs. However, RLHF's "
    "reliance on human annotators creates scalability bottlenecks: annotation costs run "
    "$2-5 per comparison, and inter-annotator agreement rarely exceeds 75%.\n\n"
    "### DPO (Direct Preference Optimization)\n\n"
    "DPO eliminates the separate reward model by directly optimizing the language model on "
    "preference pairs. This reduces training complexity and cost by approximately 40%. "
    "Benchmarks show DPO achieves comparable alignment quality to RLHF on standard evaluations "
    "(MT-Bench, AlpacaEval), with some evidence of superior performance on nuanced reasoning "
    "tasks. Variants like IPO and KTO further improve robustness to noisy preferences.\n\n"
    "### Constitutional AI and Self-Alignment\n\n"
    "Anthropic's Constitutional AI approach uses a set of principles to guide model self-critique "
    "and revision, reducing dependence on human feedback. Recent work extends this with automated "
    "red-teaming and principle discovery, where models generate and refine their own alignment "
    "criteria. The approach scales well but tends to produce overly cautious models without "
    "careful calibration of constitutional principles.\n\n"
    "### Emerging Approaches\n\n"
    "Newer methods include: debate-based alignment where models argue opposing positions; "
    "scalable oversight through recursive reward modeling; and representation engineering that "
    "directly modifies model internals to encode safety properties. Early results are promising "
    "but none has yet matched RLHF/DPO at production scale.\n\n"
    "## References\n\n"
    "- [Ouyang et al. - Training language models to follow instructions](https://arxiv.org/abs/2203.02155)\n"
    "- [Rafailov et al. - Direct Preference Optimization](https://arxiv.org/abs/2305.18290)\n"
    "- [Bai et al. - Constitutional AI](https://arxiv.org/abs/2212.08073)\n"
    "- [Burns et al. - Representation Engineering](https://arxiv.org/abs/2310.01405)\n",
    # 5: Semiconductor supply chain
    "# Global Semiconductor Supply Chain Post-CHIPS Act\n\n"
    "## Executive Summary\n\n"
    "The CHIPS and Science Act, signed in August 2022 with $52.7 billion in semiconductor "
    "subsidies, has fundamentally altered the global chip manufacturing landscape. Two years "
    "into implementation, this analysis examines the impact on TSMC, Samsung, and Intel's "
    "foundry strategies, along with broader supply chain resilience implications.\n\n"
    "## Key Findings\n\n"
    "### TSMC's US Expansion\n\n"
    "TSMC's Arizona fab complex has become the flagship CHIPS Act project, receiving $6.6 "
    "billion in direct subsidies plus $5 billion in loans. The first fab (4nm) achieved "
    "production-grade yields in late 2025, with a second fab (3nm/2nm) under construction. "
    "However, costs run 30-40% higher than comparable Taiwan facilities due to labor, "
    "permitting, and supply chain factors. TSMC has responded by expanding its Arizona "
    "investment to $65 billion with a third fab planned for advanced packaging.\n\n"
    "### Samsung and Intel Positioning\n\n"
    "Samsung's $17 billion Taylor, Texas fab focuses on advanced nodes (4nm and below), "
    "targeting both consumer electronics and automotive chips. Intel's foundry services "
    "division received the largest CHIPS Act award ($8.5 billion) to support its IDM 2.0 "
    "strategy, but the company's execution challenges - delays at Intel 18A and yield issues - "
    "have raised questions about its ability to compete with TSMC. Intel's restructuring in "
    "2025, including the potential IPO of its foundry business, signals the difficulty of the "
    "transition.\n\n"
    "### Supply Chain Resilience\n\n"
    "The concentration of advanced chip manufacturing in Taiwan remains the primary geopolitical "
    "risk. TSMC's Taiwan fabs still produce over 80% of the world's leading-edge chips. US "
    "domestic capacity will reach approximately 10% of global advanced production by 2027, "
    "insufficient for true supply chain independence but enough to sustain critical defense "
    "and infrastructure needs during a potential disruption.\n\n"
    "## References\n\n"
    "- [US Department of Commerce - CHIPS Act Awards](https://www.commerce.gov/chips)\n"
    "- [TSMC - Arizona Expansion](https://pr.tsmc.com/english/news)\n"
    "- [Semiconductor Industry Association](https://www.semiconductors.org/)\n"
    "- [Intel Foundry Services](https://www.intel.com/content/www/us/en/foundry.html)\n",
    # 6: Rust async runtimes
    "# Rust Async Runtimes: Tokio vs async-std vs smol\n\n"
    "## Executive Summary\n\n"
    "Rust's async ecosystem has matured significantly, with Tokio establishing dominance while "
    "alternatives like async-std and smol serve important niches. This guide examines the "
    "architectural differences, benchmarks performance characteristics, and provides guidance "
    "on runtime selection for different use cases.\n\n"
    "## Key Findings\n\n"
    "### Architecture Comparison\n\n"
    "**Tokio** uses a work-stealing multi-threaded scheduler with a dedicated I/O driver thread. "
    "Its architecture prioritizes throughput for high-concurrency server workloads, with features "
    "like task-local storage, cooperative scheduling budgets, and a comprehensive ecosystem "
    "(tower, hyper, tonic). The runtime handles 100K+ concurrent connections efficiently.\n\n"
    "**async-std** mirrors the standard library API surface, making it approachable for newcomers. "
    "It uses a thread-per-core model by default with a global executor. Development has slowed "
    "considerably since 2023, with the project effectively in maintenance mode.\n\n"
    "**smol** takes a minimalist approach: the entire runtime is ~1,500 lines of code. It "
    "provides basic task spawning and I/O without opinions about scheduling strategy. This "
    "makes it ideal for embedded systems, libraries that want to be runtime-agnostic, and "
    "educational purposes.\n\n"
    "### Benchmarks\n\n"
    "Testing on a 16-core server with a mix of I/O-bound and CPU-bound workloads:\n\n"
    "| Metric | Tokio | async-std | smol |\n"
    "|--------|-------|-----------|------|\n"
    "| HTTP req/s (wrk) | 485,000 | 312,000 | 289,000 |\n"
    "| Task spawn latency | 1.2\u00b5s | 2.8\u00b5s | 0.9\u00b5s |\n"
    "| Memory per 10K tasks | 4.2 MB | 6.1 MB | 3.1 MB |\n"
    "| Binary size overhead | 1.8 MB | 1.2 MB | 0.3 MB |\n\n"
    "Tokio's work-stealing scheduler excels under load imbalance. smol's lightweight design "
    "wins on memory efficiency and spawn latency.\n\n"
    "### Recommendation\n\n"
    "For production server applications, Tokio remains the clear choice - its ecosystem, "
    "documentation, and community support are unmatched. For libraries, consider using "
    "runtime-agnostic abstractions (futures crate) to avoid locking users into a specific "
    "runtime. For resource-constrained environments, smol offers the best footprint.\n\n"
    "## References\n\n"
    "- [Tokio Documentation](https://tokio.rs)\n"
    "- [async-std Book](https://book.async.rs)\n"
    "- [smol GitHub Repository](https://github.com/smol-rs/smol)\n"
    "- [Rust Async Book](https://rust-lang.github.io/async-book/)\n",
    # 7: Coastal climate adaptation
    "# Climate Adaptation for Coastal Megacities\n\n"
    "## Executive Summary\n\n"
    "Coastal megacities housing over 800 million people face escalating risks from sea level "
    "rise, storm surge intensification, and subsidence. This report evaluates engineering "
    "solutions, policy frameworks, and cost-benefit analyses for adaptation through 2050, "
    "drawing on case studies from Jakarta, Miami, Mumbai, and Shanghai.\n\n"
    "## Key Findings\n\n"
    "### Engineering Solutions\n\n"
    "Three categories of engineering intervention are being deployed at scale:\n\n"
    "**Hard infrastructure**: Sea walls, storm surge barriers, and pumping systems remain "
    "the primary defense. The Netherlands' Delta Works model is being adapted globally, with "
    "Jakarta's $40 billion National Capital Integrated Coastal Development (NCICD) and New "
    "York's $52 billion harbor barrier proposal as leading examples. Cost-effectiveness varies "
    "dramatically: $2,000-5,000 per protected meter for sea walls versus $50,000+ per meter "
    "for storm surge barriers.\n\n"
    "**Nature-based solutions**: Mangrove restoration, living shorelines, and constructed "
    "wetlands provide flood protection at 2-5x lower cost than hard infrastructure while "
    "delivering co-benefits (carbon sequestration, biodiversity, fisheries). Singapore's "
    "hybrid approach - combining mangroves with engineered structures - is emerging as a "
    "best-practice model.\n\n"
    "**Managed retreat**: For areas where protection costs exceed property values, managed "
    "retreat is increasingly recognized as necessary. The US has spent $3.4 billion on buyouts "
    "since 1989, relocating 45,000 properties. However, political feasibility remains the "
    "primary obstacle.\n\n"
    "### Cost-Benefit Analysis\n\n"
    "Global investment needs for coastal adaptation are estimated at $40-70 billion annually "
    "through 2030, rising to $100-150 billion annually by 2050. The benefit-cost ratio ranges "
    "from 4:1 for proactive adaptation in high-value areas to less than 1:1 for defending "
    "low-lying communities where retreat may be more economical. Every dollar invested in "
    "adaptation today avoids $4-8 in future damage costs.\n\n"
    "## References\n\n"
    "- [IPCC AR6 - Sea Level Rise Projections](https://www.ipcc.ch/report/ar6/wg1/)\n"
    "- [World Bank - Coastal Resilience](https://www.worldbank.org/en/topic/climatechange)\n"
    "- [C40 Cities - Climate Action Plans](https://www.c40.org/)\n"
    "- [Nature - Cost of Coastal Flooding](https://www.nature.com/articles/s41558-020-0895-y)\n"
    "- [NOAA - Sea Level Rise Viewer](https://coast.noaa.gov/slr/)\n",
    # 8: GenAI and software engineering productivity
    "# Generative AI Impact on Software Engineering Productivity\n\n"
    "## Executive Summary\n\n"
    "Generative AI coding tools - led by GitHub Copilot, Cursor, and Claude Code - have been "
    "adopted by an estimated 40% of professional developers as of early 2026. This report "
    "synthesizes empirical studies, large-scale developer surveys, and economic modeling to "
    "quantify the productivity impact and identify where AI assistance is most and least "
    "effective.\n\n"
    "## Key Findings\n\n"
    "### Empirical Studies\n\n"
    "The most rigorous controlled study (Microsoft Research, n=4,867 developers) found that "
    "Copilot users completed tasks 26% faster on average, with the effect strongest for "
    "boilerplate-heavy tasks (+55%) and weakest for complex algorithmic problems (+8%). A "
    "follow-up study at Google found similar results with Gemini-based tooling, reporting a "
    "22% reduction in code review iteration time and a 15% increase in code submission "
    "frequency.\n\n"
    "Critically, speed gains do not always translate to quality gains. Studies show a 10-15% "
    "increase in bugs per line of AI-assisted code when developers accept suggestions without "
    "careful review. The highest-performing teams use AI as a drafting tool with rigorous "
    "human review, not as an auto-accept workflow.\n\n"
    "### Developer Surveys\n\n"
    "Stack Overflow's 2025 Developer Survey (n=65,000) reports that 72% of developers using "
    "AI tools feel more productive, but only 38% report measurable output increases. The "
    "disconnect reflects AI's impact on developer satisfaction and flow state, which may "
    "not directly translate to shipping velocity. Senior developers (10+ years) report lower "
    "perceived productivity gains (18%) compared to juniors (45%), but produce higher-quality "
    "AI-assisted code.\n\n"
    "### Economic Modeling\n\n"
    "McKinsey's economic model estimates that generative AI could contribute $75-150 billion "
    "annually to the global software industry by 2030 through productivity gains. However, "
    "the distribution is uneven: the largest gains accrue to enterprises with strong CI/CD "
    "pipelines and code review practices that catch AI-introduced errors early. Companies "
    "without these safeguards may see negative ROI from AI tool adoption.\n\n"
    "## References\n\n"
    "- [GitHub - Copilot Research](https://github.blog/news-insights/research/)\n"
    "- [Microsoft Research - Developer Productivity Study](https://www.microsoft.com/en-us/research/)\n"
    "- [Stack Overflow - 2025 Developer Survey](https://survey.stackoverflow.co/)\n"
    "- [McKinsey - The Economic Potential of Generative AI](https://www.mckinsey.com/capabilities/quantumblack)\n",
    # 9: Subscription pricing behavioral economics
    "# Behavioral Economics of Subscription Pricing\n\n"
    "## Executive Summary\n\n"
    "Subscription models now underpin over $275 billion in annual consumer spending globally. "
    "This report examines how behavioral economics principles - particularly nudge theory - are "
    "applied in subscription pricing, analyzes churn prediction models, and addresses the "
    "growing ethical concerns around dark patterns in subscription management.\n\n"
    "## Key Findings\n\n"
    "### Nudge Theory Applications\n\n"
    "Subscription businesses systematically exploit cognitive biases:\n\n"
    "**Anchoring**: Presenting a high-priced annual plan alongside monthly pricing makes the "
    "annual option appear as a bargain. Netflix's tier restructuring in 2024 increased premium "
    "tier adoption by 23% by introducing an ultra-premium anchor tier.\n\n"
    "**Default bias**: Auto-renewal with opt-out cancellation leverages status quo bias. "
    "Research shows that requiring active renewal reduces retention by 35-50%, explaining "
    "why virtually all subscription services use auto-renewal.\n\n"
    "**Loss aversion**: Free trial conversions exploit the endowment effect. Users who've "
    "customized their experience during a trial (playlists, settings, saved items) convert "
    "at 2-3x the rate of passive trial users, because cancellation feels like losing something "
    "they already own.\n\n"
    "### Churn Prediction\n\n"
    "Modern churn models combine behavioral signals (login frequency, feature usage, support "
    "tickets) with payment signals (failed charges, plan downgrades, coupon usage). XGBoost "
    "and transformer-based models achieve 85-92% accuracy in predicting churn 30 days out. "
    "The most predictive single feature is declining engagement velocity - not absolute usage "
    "levels but the rate of change in usage patterns.\n\n"
    "### Ethical Considerations\n\n"
    "The FTC's 2025 enforcement actions against subscription dark patterns have established "
    "clearer boundaries. The 'click-to-cancel' rule requires that cancellation be as easy as "
    "sign-up, and the EU's Digital Services Act mandates transparent pricing and renewal "
    "notifications. Consumer advocates argue these regulations don't go far enough, pointing "
    "to practices like 'roach motel' designs where cancellation is technically possible but "
    "deliberately friction-laden.\n\n"
    "## References\n\n"
    "- [FTC - Click-to-Cancel Rule](https://www.ftc.gov/legal-library/browse/rules/negative-option-rule)\n"
    "- [Thaler & Sunstein - Nudge: The Final Edition](https://www.penguinrandomhouse.com/books/)\n"
    "- [Recurly - State of Subscriptions](https://recurly.com/research/)\n"
    "- [Harvard Business Review - Subscription Fatigue](https://hbr.org/)\n"
    "- [EU Digital Services Act](https://digital-strategy.ec.europa.eu/en/policies/digital-services-act-package)\n",
]

SAMPLE_JOBS = [
    # Today
    {
        "prompt": "Comprehensive analysis of quantum error correction breakthroughs in 2025-2026, including surface codes, topological approaches, and implications for fault-tolerant quantum computing",
        "model": "openai/o3-deep-research",
        "cost": 0.05,
        "tokens": 45200,
        "hours_ago": 2,
    },
    {
        "prompt": "Compare the economic impact of carbon border adjustment mechanisms across EU, US, and developing nations with trade flow analysis",
        "model": "gemini/deep-research",
        "cost": 0.11,
        "tokens": 62000,
        "hours_ago": 5,
    },
    {
        "prompt": "Deep dive into React Server Components vs traditional SSR: performance benchmarks, developer experience, and migration strategies",
        "model": "openai/o4-mini-deep-research",
        "cost": 0.19,
        "tokens": 38400,
        "hours_ago": 8,
    },
    # Yesterday
    {
        "prompt": "State of autonomous vehicle regulation worldwide: liability frameworks, safety standards, and insurance models as of early 2026",
        "model": "openai/o3-deep-research",
        "cost": 0.05,
        "tokens": 51000,
        "hours_ago": 18,
    },
    {
        "prompt": "Systematic review of large language model alignment techniques: RLHF, DPO, constitutional AI, and emerging approaches",
        "model": "gemini/deep-research",
        "cost": 0.1,
        "tokens": 58000,
        "hours_ago": 28,
    },
    # 2 days ago
    {
        "prompt": "Analysis of global semiconductor supply chain resilience post-CHIPS Act: TSMC, Samsung, and Intel foundry strategies",
        "model": "openai/o4-mini-deep-research",
        "cost": 0.21,
        "tokens": 42000,
        "hours_ago": 52,
    },
    {
        "prompt": "CRISPR gene therapy clinical trial outcomes 2024-2026: sickle cell, beta-thalassemia, and hereditary blindness",
        "model": "openai/o3-deep-research",
        "cost": 0.06,
        "tokens": 47500,
        "hours_ago": 55,
    },
    # 3 days ago
    {
        "prompt": "Comprehensive guide to Rust async runtime internals: Tokio vs async-std vs smol architecture comparisons",
        "model": "openai/o3-deep-research",
        "cost": 0.05,
        "tokens": 39500,
        "hours_ago": 75,
    },
    # 4 days ago
    {
        "prompt": "Climate adaptation strategies for coastal megacities: engineering solutions, policy frameworks, and cost-benefit analysis",
        "model": "gemini/deep-research",
        "cost": 0.11,
        "tokens": 67000,
        "hours_ago": 102,
    },
    # 5-6 days ago
    {
        "prompt": "Impact of generative AI on software engineering productivity: empirical studies, developer surveys, and economic modeling",
        "model": "openai/o4-mini-deep-research",
        "cost": 0.2,
        "tokens": 35000,
        "hours_ago": 125,
    },
    {
        "prompt": "Comparative analysis of central bank digital currencies: technical architectures, privacy models, and adoption timelines",
        "model": "openai/o3-deep-research",
        "cost": 0.07,
        "tokens": 52000,
        "hours_ago": 140,
    },
    # 7-8 days ago
    {
        "prompt": "Behavioral economics of subscription pricing: nudge theory applications, churn prediction models, and ethical considerations",
        "model": "openai/o3-deep-research",
        "cost": 0.06,
        "tokens": 44000,
        "hours_ago": 170,
    },
    {
        "prompt": "Advances in solid-state battery technology: energy density benchmarks, manufacturing scalability, and EV adoption impact",
        "model": "gemini/deep-research",
        "cost": 0.09,
        "tokens": 55000,
        "hours_ago": 192,
    },
    # 9-10 days ago
    {
        "prompt": "Post-quantum cryptography migration strategies for enterprise systems: NIST standards, hybrid approaches, and timeline planning",
        "model": "openai/o3-deep-research",
        "cost": 0.07,
        "tokens": 48000,
        "hours_ago": 220,
    },
    {
        "prompt": "Microplastics in human tissue: latest epidemiological findings, health risk models, and regulatory responses worldwide",
        "model": "openai/o4-mini-deep-research",
        "cost": 0.17,
        "tokens": 37000,
        "hours_ago": 240,
    },
    # 11-13 days ago
    {
        "prompt": "Nuclear fusion progress update: ITER, NIF, and private ventures - plasma confinement milestones and energy breakeven timeline",
        "model": "gemini/deep-research",
        "cost": 0.11,
        "tokens": 63000,
        "hours_ago": 268,
    },
    {
        "prompt": "WebAssembly beyond the browser: edge computing, plugin systems, and server-side adoption patterns in 2025-2026",
        "model": "openai/o3-deep-research",
        "cost": 0.04,
        "tokens": 36000,
        "hours_ago": 290,
    },
    {
        "prompt": "Global water scarcity projections 2030-2050: desalination technology advances, aquifer depletion rates, and policy interventions",
        "model": "gemini/deep-research",
        "cost": 0.09,
        "tokens": 59000,
        "hours_ago": 310,
    },
]
