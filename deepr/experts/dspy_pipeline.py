"""DSPy Pipeline Optimization for expert system.

Implements DSPy-based prompt optimization:
- Signatures for expert answer and fact checking
- Modules using ChainOfThought and ReAct
- Feedback collection for training
- Optimization with MIPROv2 or BootstrapFewShot

Note: This module provides DSPy integration when the dspy library is available.
Falls back gracefully when DSPy is not installed.

Usage:
    from deepr.experts.dspy_pipeline import ExpertAnswerSignature, DSPyExpertModule
    
    module = DSPyExpertModule(expert_name="quantum_expert")
    answer = module.forward(context="...", question="What is quantum entanglement?")
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Check if DSPy is available
try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    dspy = None


# ============================================================================
# DSPy Signatures
# ============================================================================

if DSPY_AVAILABLE:
    class ExpertAnswerSignature(dspy.Signature):
        """Signature for expert answer generation.
        
        Takes context and question, produces reasoning and answer.
        """
        context: str = dspy.InputField(desc="Retrieved context from knowledge base")
        question: str = dspy.InputField(desc="User's question")
        reasoning: str = dspy.OutputField(desc="Step-by-step reasoning process")
        answer: str = dspy.OutputField(desc="Final answer to the question")
        confidence: float = dspy.OutputField(desc="Confidence score 0-1")
    
    class FactCheckSignature(dspy.Signature):
        """Signature for fact verification.
        
        Takes a claim and context, produces verification result.
        """
        claim: str = dspy.InputField(desc="Claim to verify")
        context: str = dspy.InputField(desc="Context for verification")
        is_supported: bool = dspy.OutputField(desc="Whether claim is supported by context")
        evidence: str = dspy.OutputField(desc="Evidence supporting or refuting the claim")
        confidence: float = dspy.OutputField(desc="Confidence in verification 0-1")
    
    class QueryDecompositionSignature(dspy.Signature):
        """Signature for query decomposition.
        
        Breaks complex queries into sub-questions.
        """
        query: str = dspy.InputField(desc="Complex user query")
        sub_questions: List[str] = dspy.OutputField(desc="List of simpler sub-questions")
        reasoning: str = dspy.OutputField(desc="Why this decomposition was chosen")
    
    class SynthesisSignature(dspy.Signature):
        """Signature for answer synthesis.
        
        Combines multiple sub-answers into a coherent response.
        """
        question: str = dspy.InputField(desc="Original question")
        sub_answers: List[str] = dspy.InputField(desc="Answers to sub-questions")
        synthesis: str = dspy.OutputField(desc="Synthesized final answer")
        confidence: float = dspy.OutputField(desc="Confidence in synthesis 0-1")

else:
    # Fallback classes when DSPy is not available
    class ExpertAnswerSignature:
        """Placeholder for ExpertAnswerSignature when DSPy is not available."""
        pass
    
    class FactCheckSignature:
        """Placeholder for FactCheckSignature when DSPy is not available."""
        pass
    
    class QueryDecompositionSignature:
        """Placeholder for QueryDecompositionSignature when DSPy is not available."""
        pass
    
    class SynthesisSignature:
        """Placeholder for SynthesisSignature when DSPy is not available."""
        pass


# ============================================================================
# DSPy Modules
# ============================================================================

if DSPY_AVAILABLE:
    class ExpertAnswerModule(dspy.Module):
        """DSPy module for expert answer generation.
        
        Uses ChainOfThought for reasoning.
        """
        
        def __init__(self):
            super().__init__()
            self.answer_cot = dspy.ChainOfThought(ExpertAnswerSignature)
        
        def forward(self, context: str, question: str) -> dspy.Prediction:
            """Generate expert answer with reasoning.
            
            Args:
                context: Retrieved context
                question: User's question
                
            Returns:
                Prediction with reasoning, answer, and confidence
            """
            return self.answer_cot(context=context, question=question)
    
    class FactCheckModule(dspy.Module):
        """DSPy module for fact checking.
        
        Uses ChainOfThought for verification reasoning.
        """
        
        def __init__(self):
            super().__init__()
            self.verify_cot = dspy.ChainOfThought(FactCheckSignature)
        
        def forward(self, claim: str, context: str) -> dspy.Prediction:
            """Verify a claim against context.
            
            Args:
                claim: Claim to verify
                context: Context for verification
                
            Returns:
                Prediction with is_supported, evidence, and confidence
            """
            return self.verify_cot(claim=claim, context=context)
    
    class MultiHopExpertModule(dspy.Module):
        """DSPy module for multi-hop reasoning.
        
        Decomposes complex queries and synthesizes answers.
        """
        
        def __init__(self, retriever=None):
            super().__init__()
            self.decompose = dspy.ChainOfThought(QueryDecompositionSignature)
            self.answer = dspy.ChainOfThought(ExpertAnswerSignature)
            self.synthesize = dspy.ChainOfThought(SynthesisSignature)
            self.retriever = retriever
        
        def forward(self, question: str, context: str = "") -> dspy.Prediction:
            """Answer complex question with multi-hop reasoning.
            
            Args:
                question: Complex user question
                context: Initial context (optional)
                
            Returns:
                Prediction with synthesis and confidence
            """
            # Decompose question
            decomposition = self.decompose(query=question)
            sub_questions = decomposition.sub_questions
            
            # Answer each sub-question
            sub_answers = []
            for sub_q in sub_questions:
                # Retrieve context for sub-question if retriever available
                sub_context = context
                if self.retriever:
                    sub_context = self.retriever(sub_q)
                
                sub_answer = self.answer(context=sub_context, question=sub_q)
                sub_answers.append(sub_answer.answer)
            
            # Synthesize final answer
            synthesis = self.synthesize(
                question=question,
                sub_answers=sub_answers
            )
            
            return synthesis

else:
    # Fallback classes when DSPy is not available
    class ExpertAnswerModule:
        """Placeholder for ExpertAnswerModule when DSPy is not available."""
        
        def __init__(self):
            pass
        
        def forward(self, context: str, question: str) -> Dict[str, Any]:
            return {
                "reasoning": "DSPy not available",
                "answer": "Please install dspy to use this feature",
                "confidence": 0.0
            }
    
    class FactCheckModule:
        """Placeholder for FactCheckModule when DSPy is not available."""
        
        def __init__(self):
            pass
        
        def forward(self, claim: str, context: str) -> Dict[str, Any]:
            return {
                "is_supported": False,
                "evidence": "DSPy not available",
                "confidence": 0.0
            }
    
    class MultiHopExpertModule:
        """Placeholder for MultiHopExpertModule when DSPy is not available."""
        
        def __init__(self, retriever=None):
            pass
        
        def forward(self, question: str, context: str = "") -> Dict[str, Any]:
            return {
                "synthesis": "DSPy not available",
                "confidence": 0.0
            }


# ============================================================================
# Feedback Collection
# ============================================================================

@dataclass
class FeedbackEntry:
    """A feedback entry for training.
    
    Attributes:
        id: Unique entry identifier
        question: User's question
        context: Context used
        answer: Generated answer
        rating: User rating (good/bad or 1-5)
        feedback_text: Optional text feedback
        timestamp: When feedback was given
        expert_name: Name of the expert
    """
    question: str
    context: str
    answer: str
    rating: str  # "good", "bad", or numeric
    feedback_text: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    expert_name: str = ""
    id: str = field(default="")
    
    def __post_init__(self):
        if not self.id:
            import hashlib
            content = f"{self.question}:{self.answer}:{self.timestamp.isoformat()}"
            self.id = hashlib.sha256(content.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "context": self.context,
            "answer": self.answer,
            "rating": self.rating,
            "feedback_text": self.feedback_text,
            "timestamp": self.timestamp.isoformat(),
            "expert_name": self.expert_name
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeedbackEntry":
        return cls(
            id=data.get("id", ""),
            question=data["question"],
            context=data.get("context", ""),
            answer=data["answer"],
            rating=data["rating"],
            feedback_text=data.get("feedback_text", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            expert_name=data.get("expert_name", "")
        )
    
    def is_positive(self) -> bool:
        """Check if feedback is positive.
        
        Returns:
            True if rating indicates positive feedback
        """
        if self.rating.lower() in ["good", "positive", "helpful", "yes"]:
            return True
        try:
            numeric = float(self.rating)
            return numeric >= 3.5  # Assuming 1-5 scale
        except ValueError:
            return False


class FeedbackCollector:
    """Collects and manages feedback for DSPy optimization.
    
    Attributes:
        expert_name: Name of the expert
        storage_path: Path for feedback storage
        entries: List of feedback entries
    """
    
    def __init__(
        self,
        expert_name: str,
        storage_dir: Optional[Path] = None
    ):
        """Initialize feedback collector.
        
        Args:
            expert_name: Name of the expert
            storage_dir: Directory for storage
        """
        self.expert_name = expert_name
        
        if storage_dir is None:
            storage_dir = Path("data/experts") / expert_name / "feedback"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.storage_path = self.storage_dir / "feedback.json"
        self.entries: List[FeedbackEntry] = []
        
        self._load()
    
    def add_feedback(
        self,
        question: str,
        context: str,
        answer: str,
        rating: str,
        feedback_text: str = ""
    ) -> FeedbackEntry:
        """Add feedback entry.
        
        Args:
            question: User's question
            context: Context used
            answer: Generated answer
            rating: User rating
            feedback_text: Optional text feedback
            
        Returns:
            Created FeedbackEntry
        """
        entry = FeedbackEntry(
            question=question,
            context=context,
            answer=answer,
            rating=rating,
            feedback_text=feedback_text,
            expert_name=self.expert_name
        )
        
        self.entries.append(entry)
        self._save()
        
        return entry
    
    def get_training_examples(
        self,
        positive_only: bool = False,
        min_entries: int = 10
    ) -> List[Dict[str, Any]]:
        """Get training examples for DSPy optimization.
        
        Args:
            positive_only: Only include positive feedback
            min_entries: Minimum entries required
            
        Returns:
            List of training examples
        """
        if len(self.entries) < min_entries:
            return []
        
        examples = []
        for entry in self.entries:
            if positive_only and not entry.is_positive():
                continue
            
            examples.append({
                "question": entry.question,
                "context": entry.context,
                "answer": entry.answer,
                "rating": entry.rating
            })
        
        return examples
    
    def get_stats(self) -> Dict[str, Any]:
        """Get feedback statistics.
        
        Returns:
            Dictionary with stats
        """
        positive = sum(1 for e in self.entries if e.is_positive())
        negative = len(self.entries) - positive
        
        return {
            "total_entries": len(self.entries),
            "positive_count": positive,
            "negative_count": negative,
            "positive_rate": positive / len(self.entries) if self.entries else 0,
            "oldest_entry": min(e.timestamp for e in self.entries).isoformat() if self.entries else None,
            "newest_entry": max(e.timestamp for e in self.entries).isoformat() if self.entries else None
        }
    
    def _save(self):
        """Save feedback to disk."""
        data = [e.to_dict() for e in self.entries]
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def _load(self):
        """Load feedback from disk."""
        if self.storage_path.exists():
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.entries = [FeedbackEntry.from_dict(e) for e in data]


# ============================================================================
# DSPy Optimization
# ============================================================================

@dataclass
class OptimizationResult:
    """Result of DSPy optimization.
    
    Attributes:
        success: Whether optimization succeeded
        method: Optimization method used
        num_examples: Number of training examples used
        metrics_before: Metrics before optimization
        metrics_after: Metrics after optimization
        optimized_at: When optimization was performed
        error: Error message if failed
    """
    success: bool
    method: str
    num_examples: int = 0
    metrics_before: Dict[str, float] = field(default_factory=dict)
    metrics_after: Dict[str, float] = field(default_factory=dict)
    optimized_at: datetime = field(default_factory=datetime.utcnow)
    error: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "method": self.method,
            "num_examples": self.num_examples,
            "metrics_before": self.metrics_before,
            "metrics_after": self.metrics_after,
            "optimized_at": self.optimized_at.isoformat(),
            "error": self.error
        }


class DSPyOptimizer:
    """Optimizer for DSPy modules using MIPROv2 or BootstrapFewShot.
    
    Attributes:
        expert_name: Name of the expert
        feedback_collector: Feedback collector for training data
        storage_dir: Directory for storing optimized prompts
    """
    
    def __init__(
        self,
        expert_name: str,
        feedback_collector: Optional[FeedbackCollector] = None,
        storage_dir: Optional[Path] = None
    ):
        """Initialize DSPy optimizer.
        
        Args:
            expert_name: Name of the expert
            feedback_collector: Feedback collector for training data
            storage_dir: Directory for storage
        """
        self.expert_name = expert_name
        self.feedback_collector = feedback_collector or FeedbackCollector(expert_name)
        
        if storage_dir is None:
            storage_dir = Path("data/experts") / expert_name / "dspy"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.optimized_prompts_path = self.storage_dir / "optimized_prompts.json"
        self.optimization_history_path = self.storage_dir / "optimization_history.json"
    
    def optimize(
        self,
        module: Any,
        method: str = "bootstrap",
        min_examples: int = 10,
        metric_fn: Optional[callable] = None
    ) -> OptimizationResult:
        """Optimize a DSPy module.
        
        Args:
            module: DSPy module to optimize
            method: Optimization method ("bootstrap", "mipro", "auto")
            min_examples: Minimum training examples required
            metric_fn: Custom metric function for evaluation
            
        Returns:
            OptimizationResult with success status and metrics
        """
        if not DSPY_AVAILABLE:
            return OptimizationResult(
                success=False,
                method=method,
                error="DSPy not available. Install with: pip install dspy-ai"
            )
        
        # Get training examples
        examples = self.feedback_collector.get_training_examples(
            positive_only=True,
            min_entries=min_examples
        )
        
        if len(examples) < min_examples:
            return OptimizationResult(
                success=False,
                method=method,
                num_examples=len(examples),
                error=f"Insufficient training examples: {len(examples)} < {min_examples}"
            )
        
        try:
            # Convert to DSPy examples
            trainset = self._create_trainset(examples)
            
            # Select optimization method
            if method == "auto":
                method = "mipro" if len(examples) >= 50 else "bootstrap"
            
            # Run optimization
            if method == "mipro":
                optimized_module, metrics = self._optimize_mipro(
                    module, trainset, metric_fn
                )
            else:
                optimized_module, metrics = self._optimize_bootstrap(
                    module, trainset, metric_fn
                )
            
            # Save optimized prompts
            self._save_optimized_module(optimized_module)
            
            result = OptimizationResult(
                success=True,
                method=method,
                num_examples=len(examples),
                metrics_after=metrics
            )
            
            # Record in history
            self._record_optimization(result)
            
            return result
            
        except Exception as e:
            return OptimizationResult(
                success=False,
                method=method,
                num_examples=len(examples),
                error=str(e)
            )
    
    def _create_trainset(self, examples: List[Dict[str, Any]]) -> List[Any]:
        """Create DSPy trainset from examples.
        
        Args:
            examples: List of training examples
            
        Returns:
            DSPy-compatible trainset
        """
        if not DSPY_AVAILABLE:
            return []
        
        trainset = []
        for ex in examples:
            trainset.append(dspy.Example(
                question=ex["question"],
                context=ex.get("context", ""),
                answer=ex["answer"]
            ).with_inputs("question", "context"))
        
        return trainset
    
    def _optimize_bootstrap(
        self,
        module: Any,
        trainset: List[Any],
        metric_fn: Optional[callable] = None
    ) -> Tuple[Any, Dict[str, float]]:
        """Optimize using BootstrapFewShot.
        
        Args:
            module: Module to optimize
            trainset: Training examples
            metric_fn: Metric function
            
        Returns:
            Tuple of (optimized_module, metrics)
        """
        if metric_fn is None:
            metric_fn = self._default_metric
        
        # Use BootstrapFewShot teleprompter
        teleprompter = dspy.BootstrapFewShot(
            metric=metric_fn,
            max_bootstrapped_demos=4,
            max_labeled_demos=8
        )
        
        optimized = teleprompter.compile(module, trainset=trainset)
        
        # Evaluate
        metrics = self._evaluate(optimized, trainset, metric_fn)
        
        return optimized, metrics
    
    def _optimize_mipro(
        self,
        module: Any,
        trainset: List[Any],
        metric_fn: Optional[callable] = None
    ) -> Tuple[Any, Dict[str, float]]:
        """Optimize using MIPROv2.
        
        Args:
            module: Module to optimize
            trainset: Training examples
            metric_fn: Metric function
            
        Returns:
            Tuple of (optimized_module, metrics)
        """
        if metric_fn is None:
            metric_fn = self._default_metric
        
        # Check if MIPROv2 is available
        if hasattr(dspy, 'MIPROv2'):
            teleprompter = dspy.MIPROv2(
                metric=metric_fn,
                num_candidates=10,
                init_temperature=1.0
            )
        elif hasattr(dspy, 'MIPRO'):
            # Fall back to MIPRO if MIPROv2 not available
            teleprompter = dspy.MIPRO(
                metric=metric_fn,
                num_candidates=10
            )
        else:
            # Fall back to BootstrapFewShot
            return self._optimize_bootstrap(module, trainset, metric_fn)
        
        optimized = teleprompter.compile(
            module,
            trainset=trainset,
            num_trials=20
        )
        
        # Evaluate
        metrics = self._evaluate(optimized, trainset, metric_fn)
        
        return optimized, metrics
    
    def _default_metric(self, example: Any, prediction: Any, trace=None) -> float:
        """Default metric for optimization.
        
        Compares predicted answer to expected answer.
        
        Args:
            example: Training example
            prediction: Model prediction
            trace: Optional trace
            
        Returns:
            Score between 0 and 1
        """
        if not hasattr(prediction, 'answer'):
            return 0.0
        
        expected = example.answer.lower().strip()
        predicted = prediction.answer.lower().strip()
        
        # Simple overlap score
        expected_words = set(expected.split())
        predicted_words = set(predicted.split())
        
        if not expected_words:
            return 1.0 if not predicted_words else 0.0
        
        overlap = len(expected_words & predicted_words)
        return overlap / len(expected_words)
    
    def _evaluate(
        self,
        module: Any,
        testset: List[Any],
        metric_fn: callable
    ) -> Dict[str, float]:
        """Evaluate module on test set.
        
        Args:
            module: Module to evaluate
            testset: Test examples
            metric_fn: Metric function
            
        Returns:
            Dictionary of metrics
        """
        scores = []
        for example in testset[:20]:  # Limit evaluation size
            try:
                prediction = module(
                    question=example.question,
                    context=example.context
                )
                score = metric_fn(example, prediction)
                scores.append(score)
            except Exception:
                scores.append(0.0)
        
        return {
            "accuracy": sum(scores) / len(scores) if scores else 0.0,
            "num_evaluated": len(scores)
        }
    
    def _save_optimized_module(self, module: Any):
        """Save optimized module prompts.
        
        Args:
            module: Optimized DSPy module
        """
        try:
            # Extract prompts from module
            prompts = {}
            if hasattr(module, 'dump_state'):
                prompts = module.dump_state()
            elif hasattr(module, 'demos'):
                prompts = {"demos": [str(d) for d in module.demos]}
            
            with open(self.optimized_prompts_path, 'w', encoding='utf-8') as f:
                json.dump(prompts, f, indent=2, default=str)
        except Exception:
            pass  # Best effort save
    
    def load_optimized_module(self, module: Any) -> Any:
        """Load optimized prompts into module.
        
        Args:
            module: Module to load prompts into
            
        Returns:
            Module with loaded prompts
        """
        if not self.optimized_prompts_path.exists():
            return module
        
        try:
            with open(self.optimized_prompts_path, 'r', encoding='utf-8') as f:
                prompts = json.load(f)
            
            if hasattr(module, 'load_state'):
                module.load_state(prompts)
        except Exception:
            pass  # Best effort load
        
        return module
    
    def _record_optimization(self, result: OptimizationResult):
        """Record optimization in history.
        
        Args:
            result: Optimization result
        """
        history = []
        if self.optimization_history_path.exists():
            with open(self.optimization_history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        history.append(result.to_dict())
        
        # Keep last 50 optimizations
        history = history[-50:]
        
        with open(self.optimization_history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)
    
    def get_optimization_history(self) -> List[Dict[str, Any]]:
        """Get optimization history.
        
        Returns:
            List of past optimization results
        """
        if not self.optimization_history_path.exists():
            return []
        
        with open(self.optimization_history_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def should_optimize(
        self,
        min_new_examples: int = 20,
        days_since_last: int = 7
    ) -> Tuple[bool, str]:
        """Check if optimization should be run.
        
        Args:
            min_new_examples: Minimum new examples since last optimization
            days_since_last: Minimum days since last optimization
            
        Returns:
            Tuple of (should_optimize, reason)
        """
        history = self.get_optimization_history()
        stats = self.feedback_collector.get_stats()
        
        # Check if enough examples
        if stats["total_entries"] < 10:
            return False, f"Insufficient examples: {stats['total_entries']} < 10"
        
        # Check if never optimized
        if not history:
            return True, "Never optimized before"
        
        # Check time since last optimization
        last_opt = datetime.fromisoformat(history[-1]["optimized_at"])
        days_elapsed = (datetime.utcnow() - last_opt).days
        
        if days_elapsed >= days_since_last:
            return True, f"{days_elapsed} days since last optimization"
        
        # Check new examples since last optimization
        last_examples = history[-1].get("num_examples", 0)
        new_examples = stats["total_entries"] - last_examples
        
        if new_examples >= min_new_examples:
            return True, f"{new_examples} new examples since last optimization"
        
        return False, f"Not enough new data: {new_examples} < {min_new_examples}"
