from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI


def _call_with_backoff(fn, max_retries: int = 5, base_delay: float = 1.0):
    """
    Very small retry helper for hackathon demos.
    Retries on any Exception to keep things simple.
    """
    last_err = None
    for i in range(max_retries):
        try:
            return fn()
        except Exception as e:  # noqa
            last_err = e
            if i == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** i))
    raise last_err  # type: ignore[misc]


def _truncate(text: str, max_chars: int = 12000) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 200] + "\n\n...(truncated)...\n"


def _ensure_three_key_points(items: Any) -> List[str]:
    points = [str(x).strip() for x in (items or []) if str(x).strip()]
    return points[:3]


def _polish_hook(hook: str, fallback: str = "") -> str:
    text = (hook or "").strip() or (fallback or "").strip()
    if not text:
        return ""
    text = text.replace("?", "").replace("？", "").strip()
    if not text:
        text = (fallback or "").strip()
    if text and text[-1] not in ".!":
        text += "."
    return text


def _why_section(metrics: Dict[str, Any]) -> str:
    visits = float(metrics.get("visits", 0) or 0)
    dwell = float(metrics.get("avg_dwell_sec", 0) or 0)
    raw_score = metrics.get("engagement_score")
    score = (
        f"{float(raw_score):.3f}"
        if raw_score is not None and str(raw_score).strip() != ""
        else "데이터 없음"
    )
    return (
        f"왜 뜨는가: 방문 {visits:.0f}회와 평균 체류 {dwell:.1f}초는 실제 소비가 일어난 신호입니다. "
        f"참여도 점수 {score}를 보면 단순 노출을 넘어 관심이 유지된 주제로 해석됩니다."
    )


def _discussion_prompt() -> str:
    return "조회수와 체류시간 중 어떤 지표가 더 신뢰할 만한가요?"


def _lang_instruction(language: str) -> str:
    """Return a short 'write in X' instruction.

    We keep this lightweight and deterministic to avoid extra calls.
    """
    lang = (language or "").strip().lower()
    if "-" in lang:
        lang = lang.split("-", 1)[0]
    return {
        "ko": "반드시 한국어로 작성하라.",
        "en": "Write in English.",
        "ja": "日本語で書いてください。",
        "es": "Escribe en español.",
        "zh": "用简体中文书写。",
        "zh-hans": "用简体中文书写。",
        "zh-hant": "用繁體中文書寫。",
        "fr": "Écris en français.",
        "de": "Schreibe auf Deutsch.",
        "pt": "Escreva em português.",
        "id": "Tulis dalam Bahasa Indonesia.",
        "vi": "Viết bằng tiếng Việt.",
        "th": "เขียนเป็นภาษาไทย",
        "hi": "Write in Hindi.",
        "ar": "اكتب باللغة العربية.",
    }.get(lang, "Write in English.")


def _age_profile(age_group: str) -> str:
    """Return guidance for writing style based on audience age/lifestage.

    age_group is a short code:
    - elem, mid, high, uni, 20s, 30s, general
    """
    a = (age_group or "").strip().lower()
    profiles = {
        "elem": "Elementary school (approx 8–12). Use very simple words, short sentences. Use allowance/coins/piggy bank examples. Avoid adult topics. No investment or credit advice. Include gentle encouragement.",
        "mid": "Middle school (approx 13–15). Simple language, relatable examples: snacks, games, small subscriptions. Focus on habits and basic budgeting. Avoid adult financial products.",
        "high": "High school (approx 16–18). Clear, practical, still easy. Examples: transportation, academy fees, part-time work. Focus on budgeting and saving habits. Avoid risky investing guidance.",
        "uni": "College student. Practical and friendly. Examples: rent, subscriptions, delivery, part-time income. Include a simple system and a checklist.",
        "20s": "In your 20s. Friendly but efficient. Examples: first salary, subscriptions, credit card, emergency fund. Include a simple framework and next actions.",
        "30s": "In your 30s. Calm, pragmatic. Examples: household budget, housing, insurance, long-term goals. Include a structured checklist and risk notes.",
        "general": "General audience. Keep it simple and widely relatable.",
    }
    return profiles.get(a, profiles["general"])


def _age_guardrails(age_group: str) -> str:
    a = (age_group or "").strip().lower()
    if a in {"elem", "mid", "high"}:
        return (
            "Safety/ethics: The audience is a minor. Avoid adult-only topics (alcohol, gambling, etc.). "
            "Do not give investment/loan/credit product recommendations. Keep it educational and habit-focused. "
            "If relevant, suggest discussing with a parent/guardian."
        )
    return "Safety/ethics: Keep claims factual. Avoid medical/legal/financial guarantees. Provide general, educational guidance."



class OpenAIService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-5.2",
        embedding_model: str = "text-embedding-3-small",
    ):
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. (환경변수 또는 UI에서 입력)")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.embedding_model = embedding_model

    def summarize(
        self,
        *,
        url: str,
        title: str,
        content: str,
        metrics: Optional[Dict[str, Any]] = None,
        language: str = "ko",
        age_group: str = "general",
    ) -> Dict[str, Any]:
        """
        Returns a dict that matches the schema below (Structured Outputs).
        Uses Responses API + text.format(json_schema).
        """
        content = _truncate(content, max_chars=14000)
        metrics = metrics or {}

        schema = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1},
                "localized_title": {"type": "string", "minLength": 1},
                "hook": {"type": "string"},
                "one_liner": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                "why_trending": {"type": "string"},
                "discussion_prompt": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
                "sources": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
            },
            "required": [
                "url",
                "title",
                "localized_title",
                "hook",
                "one_liner",
                "key_points",
                "why_trending",
                "discussion_prompt",
                "summary",
                "tags",
                "sources",
            ],
            "additionalProperties": False,
        }

        system = (
            "You are a product/content strategist and editor. "
            "Summarize what people truly linger on, and propose angles for repurposing. "
            "Avoid hallucinations; if uncertain, stay neutral and explicit about uncertainty. "
            "Hook must be declarative (no question form), punchy, curiosity-driven, and factual. "
            "Return at most 3 key_points. "
            "why_trending must be 1-2 sentences grounded in visits, avg_dwell_sec, engagement_score. "
            "discussion_prompt must be one short, safe sentence for minors. "
            + _age_profile(age_group)
            + " "
            + _age_guardrails(age_group)
            + " "
            + _lang_instruction(language)
        )

        user = f"""
[메타데이터]
- URL: {url}
- 추정 제목: {title or "(unknown)"}
- 독자 연령/라이프스테이지: {age_group}
- 메트릭: {json.dumps(metrics, ensure_ascii=False)}

[작성 규칙]
- localized_title: 현재 언어({language})로 자연스럽고 클릭을 부르는 제목(과장 금지)
- hook: 카드에서 클릭을 유도하는 1문장(사실 기반, 10~22단어/글자 권장)
- one_liner: 핵심 요지 1문장
- key_points: 짧은 불릿 3~8개
- tags: 검색/추천에 유리한 키워드 3~10개

[원문 텍스트]
{content}
""".strip()

        def _do():
            return self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # Structured Outputs for Responses API
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "staypick_summary",
                        "schema": schema,
                        "strict": True,
                    }
                },
                store=False,
            )

        resp = _call_with_backoff(_do)
        raw = resp.output_text
        data = json.loads(raw)
        data["url"] = url
        # Backward-compat: if localized_title missing, reuse title
        if not data.get("localized_title"):
            data["localized_title"] = data.get("title") or title
        data["key_points"] = _ensure_three_key_points(data.get("key_points"))
        if not data["key_points"]:
            data["key_points"] = [data.get("one_liner") or "핵심 포인트를 확인하세요."]
        data["hook"] = _polish_hook(data.get("hook", ""), fallback=data.get("one_liner", ""))
        why_text = _why_section(metrics)
        data["why_trending"] = (data.get("why_trending") or "").strip() or why_text
        data["discussion_prompt"] = (data.get("discussion_prompt") or "").strip() or _discussion_prompt()
        data["summary"] = (data.get("summary") or "").strip() or data["why_trending"]
        sources = [str(x).strip() for x in (data.get("sources") or []) if str(x).strip()]
        if url not in sources:
            sources.insert(0, url)
        data["sources"] = sources[:5]
        return data

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        def _do():
            return self.client.embeddings.create(
                model=self.embedding_model,
                input=list(texts),
            )

        resp = _call_with_backoff(_do)
        return [d.embedding for d in resp.data]

    def web_trends(self, query: str, language: str = "ko") -> str:
        """
        Optional: uses built-in web_search tool via Responses API.
        """
        query = (query or "").strip()
        if not query:
            return ""

        prompt = (
            "다음 키워드/주제에 대해 '최근 트렌드' 관점에서 참고할 만한 핵심 이슈 5개를 뽑고, "
            "각 이슈를 2~3문장으로 요약해줘. "
            + _lang_instruction(language)
            + "\n\n"
            f"키워드: {query}"
        )

        def _do():
            return self.client.responses.create(
                model=self.model,
                tools=[{"type": "web_search"}],
                input=prompt,
                store=False,
            )

        resp = _call_with_backoff(_do)
        return resp.output_text

    def generate_content(
        self,
        *,
        summaries: List[Dict[str, Any]],
        persona: str,
        output_format: str,
        additional_context: str = "",
        external_trends: str = "",
        language: str = "ko",
        age_group: str = "general",
    ) -> str:
        """
        Produces a new piece of content in Markdown.
        """
        if not summaries:
            raise ValueError("summaries가 비어있습니다")

        # Keep prompt size in check
        compact_items = []
        for s in summaries:
            compact_items.append(
                {
                    "title": s.get("title"),
                    "url": s.get("url"),
                    "one_liner": s.get("one_liner"),
                    "key_points": s.get("key_points"),
                    "tags": s.get("tags"),
                    "recommended_angles": s.get("recommended_angles"),
                    "metrics": s.get("metrics"),
                }
            )

        system = (
            "You are a content editor specialized in repurposing research into original content. "
            "Never copy-paste long passages; rewrite meaningfully. Output must be Markdown. "
            + _age_profile(age_group)
            + " "
            + _age_guardrails(age_group)
            + " "
            + _lang_instruction(language)
        )

        user = f"""
[목표 페르소나]
{persona}

[독자 연령/라이프스테이지]
{age_group}

[원하는 산출물 포맷]
{output_format}

[내부 '체류시간 상위' 콘텐츠 인사이트]
{json.dumps(compact_items, ensure_ascii=False)}

[외부 트렌드 참고(있을 경우)]
{external_trends or "(없음)"}

[추가 컨텍스트/브랜드 톤]
{additional_context or "(없음)"}

요구사항:
1) 독자({age_group}) + {persona}가 관심 가질 만한 '훅(첫 문단/첫 문장)'을 강하게. (과장 금지)
2) 읽기 쉬운 섹션 구조(H2/H3).
3) 실행 가능한 체크리스트/다음 액션 포함.
4) 마지막에 "Sources" 섹션을 만들고, 위 URL을 불릿으로 나열(간단 코멘트 1줄씩).
""".strip()

        def _do():
            return self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                store=False,
            )

        resp = _call_with_backoff(_do)
        return resp.output_text
