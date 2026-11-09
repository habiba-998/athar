"""Explanation layer.

Evidence and calculations come from the deterministic engine. This module only
*narrates* them. The template narrative is always produced; an optional LLM
narrative is returned in a separate field and is never used to create findings
or trigger actions. The LLM receives only the structured facts below.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .models import Environment

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"  # fixed host: no user-controlled URL (SSRF-safe)
EVIDENCE_AR = {"validated": "مؤكَّد", "observed": "مرصود", "inferred": "مستنتَج", "theoretical": "نظري"}
SEV_AR = {"critical": "حرج", "high": "مرتفع", "medium": "متوسط", "low": "منخفض"}


def _name(env: Environment, asset_id: str, lang: str) -> str:
    a = env.asset(asset_id)
    return a.name_ar if lang == "ar" else a.name


def path_facts(env: Environment, path: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": [env.asset(n).name for n in path["nodes"]],
        "target": env.asset(path["target"]).name,
        "target_criticality": env.asset(path["target"]).criticality,
        "score": path["score"], "severity": path["severity"], "classification": path["classification"],
        "steps": path["steps"], "factors": path["factors"],
    }


def template_path(env: Environment, path: dict[str, Any], lang: str) -> str:
    route = " → ".join(_name(env, n, lang) for n in path["nodes"])
    hops = len(path["steps"])
    if lang == "ar":
        cls = {"validated": "جميع الحلقات مؤكَّدة الاستغلال (ضمن البيانات الافتراضية).",
               "observed": "جميع الحلقات مرصودة مباشرة في مصدر بيانات لكنها غير مؤكَّدة بشكل مستقل.",
               "inferred": "بعض الحلقات مستنتَجة من الإعدادات وغير مؤكَّدة.",
               "theoretical": "المسار نظري: توجد حلقة واحدة على الأقل لم يتم التحقق منها."}[path["classification"]]
        return (f"المسار: {route}. يصل المهاجم المفترض إلى «{_name(env, path['target'], lang)}» "
                f"عبر {hops} خطوات. الدرجة {path['score']} من 100 ({SEV_AR[path['severity']]}). {cls} "
                "الدرجة مؤشر استدلالي قابل لإعادة الحساب وليست احتمالاً للاختراق.")
    cls = {"validated": "Every hop is validated as exploitable (within the synthetic data).",
           "observed": "Every hop is observed directly in a data source but not independently validated.",
           "inferred": "Some hops are inferred from configuration and not validated.",
           "theoretical": "The path is theoretical: at least one hop is unverified."}[path["classification"]]
    return (f"Route: {route}. A compromised identity could reach \"{_name(env, path['target'], lang)}\" "
            f"in {hops} steps. Score {path['score']}/100 ({path['severity']}). {cls} "
            "The score is a reproducible heuristic index, not a probability of compromise.")


def template_recommendation(env: Environment, rec: dict[str, Any], lang: str) -> str:
    act = rec["action"]
    rid = act.get("relationship_id")
    rel = next((r for r in env.relationships if r.id == rid), None)
    subj = (f"{_name(env, rel.source, lang)} → {_name(env, rel.target, lang)}" if rel
            else _name(env, act["asset_id"], lang))
    elim, mit, lvl = rec["paths_eliminated"], rec["paths_mitigated"], rec["tradeoff"]
    if lang == "ar":
        return (f"الإجراء المقترح ({act['kind']}) على: {subj}. تُظهر المحاكاة إزالة {elim} مسارات وتخفيف {mit} "
                f"مسارات (تخفيض {rec['path_score_reduction_pct']}٪ في مجموع درجات المسارات و"
                f"{rec['risk_reduction_pct']}٪ في مؤشر الوضع الأمني). الأثر التشغيلي: {lvl}. "
                "يتطلب تنفيذ أي تغيير فعلي موافقة بشرية.")
    return (f"Proposed action ({act['kind']}) on: {subj}. Simulation shows {elim} path(s) eliminated and "
            f"{mit} mitigated ({rec['path_score_reduction_pct']}% lower summed path score, "
            f"{rec['risk_reduction_pct']}% lower posture index). "
            f"Operational impact: {lvl}. Any real-world change requires human approval.")


MAX_AI_CHARS = 1500


def ai_status() -> dict[str, Any]:
    """Public AI configuration state. Never exposes the key."""
    provider = os.environ.get("ATHAR_AI_PROVIDER")
    if provider != "anthropic":
        return {"enabled": False, "provider": None, "reason": "ai_disabled"}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"enabled": False, "provider": "anthropic", "reason": "ai_not_configured"}
    return {"enabled": True, "provider": "anthropic", "reason": "ok"}


def ai_narrative(facts: dict[str, Any], lang: str) -> tuple[str | None, str | None]:
    """Optional LLM narration. Returns (text, error_code). Disabled unless configured.

    Any failure (network, bad status, malformed or empty response) yields (None, "ai_unavailable"):
    the deterministic explanation is always returned alongside, and nothing is invented.
    """
    status = ai_status()
    if not status["enabled"]:
        return None, str(status["reason"])
    key = os.environ["ANTHROPIC_API_KEY"]
    body = json.dumps({
        "model": os.environ.get("ATHAR_AI_MODEL", "claude-haiku-5-5"),
        "max_tokens": 400,
        "system": ("You explain defensive security findings. Use ONLY the JSON facts provided. "
                   "Do not add findings, numbers or actions not present. Do not give attack instructions. "
                   f"Answer in {'Arabic' if lang == 'ar' else 'English'} in under 120 words."),
        "messages": [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
    }).encode()
    req = urllib.request.Request(ANTHROPIC_URL, data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed https host
            data = json.loads(resp.read(200_000))
        text = "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict)).strip()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, AttributeError, TypeError):
        return None, "ai_unavailable"
    if not text:
        return None, "ai_unavailable"
    return text[:MAX_AI_CHARS], None
