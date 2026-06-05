"""
Multi-model routing - picks the right model for each task type.
"""
from config import DEFAULT_MODEL

ROUTING_RULES = {
    "vision":   ["moondream", "llava"],           # has image
    "long":     ["gemma3n-local", "qwen2.5"],     # long analysis
    "fast":     ["qwen2.5"],                      # quick chat
    "code":     ["gemma3n-local", "qwen2.5"],     # code tasks
    "default":  ["qwen2.5", "gemma3n-local"],
}

def route_model(prompt, has_image=False, available_models=None):
    """Pick the best available model for the task."""
    if available_models is None:
        available_models = [DEFAULT_MODEL]

    def first_available(candidates):
        for c in candidates:
            for m in available_models:
                if c in m.lower():
                    return m
        return available_models[0] if available_models else DEFAULT_MODEL

    if has_image:
        return first_available(ROUTING_RULES["vision"])

    p = prompt.lower()
    if any(w in p for w in ["def ","import ","class ","function","code","script","python","bash"]):
        return first_available(ROUTING_RULES["code"])
    if len(prompt) > 500:
        return first_available(ROUTING_RULES["long"])

    return first_available(ROUTING_RULES["fast"])

def get_model_capabilities(model_name):
    m = model_name.lower()
    return {
        "vision": any(v in m for v in ["moondream","llava","vision","bakllava"]),
        "fast":   any(v in m for v in ["gemma","phi","tiny"]),
        "strong": any(v in m for v in ["gemma3n","llama","mixtral"]),
    }
