"""Public API for the Graph-Based Blockage Risk Propagation Model."""

from .core import derive_susceptibility, evaluate_gbbrpm

__all__ = ["derive_susceptibility", "evaluate_gbbrpm"]
__version__ = "0.1.0"
