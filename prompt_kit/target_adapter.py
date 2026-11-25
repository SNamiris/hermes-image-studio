"""Translate numeric emphasis between NovelAI and ComfyUI."""

import re


TARGETS = ("raw", "nai", "comfyui")
_WEIGHT = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
_NAI = re.compile(rf"(?<![\w.])({_WEIGHT})::(.+?)::")
_COMFYUI = re.compile(rf"\(((?:[^()]|\([^()]*\))+?):({_WEIGHT})\)")


def adapt_prompt(prompt: str, target: str) -> str:
    if target == "nai":
        return _COMFYUI.sub(r"\2::\1::", prompt)
    if target == "comfyui":
        return _NAI.sub(r"(\2:\1)", prompt)
    return prompt
