"""
Legacy Sklearn Predictor
Replaces SetFit to use the original srt-ml pickle model.
"""

import sys
import logging
import time
from typing import List, Dict, Any
from pathlib import Path
import joblib

# Patch legacy scikit-learn namespaces for current versions
import sklearn.feature_selection
import sklearn.linear_model._stochastic_gradient
sys.modules['sklearn.feature_selection.univariate_selection'] = sklearn.feature_selection
sys.modules['sklearn.linear_model.stochastic_gradient'] = sklearn.linear_model._stochastic_gradient

logger = logging.getLogger(__name__)

_model = None

def _load_model(model_path: str = None):
    global _model
    if _model is not None:
        return
        
    if model_path is None:
        model_path = str(Path(__file__).parent / "data" / "legacy_model.pkl")
        
    logger.info(f"[Sklearn] Loading legacy model from {model_path}")
    t0 = time.time()
    
    # Needs imbalanced-learn and dill installed in the environment
    _model = joblib.load(model_path)
    
    elapsed = round((time.time() - t0) * 1000)
    logger.info(f"[Sklearn] Model loaded in {elapsed}ms")

def predict_solicitation(
    file_texts: List[Dict[str, str]],
    model_path: str = None,
) -> Dict[str, Any]:
    
    _load_model(model_path)
    t0 = time.time()
    
    # Combine texts
    all_texts = [ft.get("text", "") for ft in file_texts if ft.get("text", "").strip()]
    
    if not all_texts:
        return {
            "prediction": "non_compliant",
            "confidence": 0.0,
            "is_508_applicable": False,
            "includes_508": False,
            "prediction_source": "sklearn_legacy",
            "signal_text": "",
            "duration_ms": round((time.time() - t0) * 1000),
        }

    combined = " ".join(all_texts)
    
    # Predict
    label = _model.predict([combined])[0]
    
    # Provide a dummy confidence unless probability is available
    confidence = 1.0 if label == 1 else 0.0
    try:
        if hasattr(_model, "predict_proba"):
            probs = _model.predict_proba([combined])
            confidence = float(probs[0][label])
        elif hasattr(_model, "decision_function"):
            scores = _model.decision_function([combined])
            # Simple scaling to keep within 0-1
            import math
            confidence = 1 / (1 + math.exp(-scores[0])) 
    except Exception as e:
        logger.warning(f"Could not compute probabilities: {e}")

    is_compliant = bool(label == 1)
    elapsed = round((time.time() - t0) * 1000)
    
    logger.info(f"[Sklearn] Prediction: {'compliant' if is_compliant else 'non_compliant'} "
                f"(confidence={confidence:.3f}, {elapsed}ms)")

    return {
        "prediction": "compliant" if is_compliant else "non_compliant",
        "confidence": confidence,
        "is_508_applicable": True,
        "includes_508": is_compliant,
        "prediction_source": "sklearn_legacy",
        "signal_text": combined[:500],
        "duration_ms": elapsed,
    }
