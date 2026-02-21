from __future__ import annotations

import html
import io
import zipfile
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from core.subscription import subscription_snapshot
from modules.metrics import topk_per_category


def render_admin_global(ctx: Dict[str, Any]) -> None:
    t = ctx["t"]
    api_key = ctx["api_key"]
    normalize_lang = ctx["normalize_lang"]
    SEOPage = ctx["SEOPage"]
    render_html = ctx["render_html"]
    slugify = ctx["slugify"]
    cached_fetch = ctx["cached_fetch"]
    build_demo_summary = ctx["build_demo_summary"]
    snippet_from_content = ctx["snippet_from_content"]
    ensure_ai = ctx["ensure_ai"]

    sub_global = subscription_snapshot()
    programmatic_seo_enabled = sub_global.get("tier") == "pro"
    st.subheader("🌍 글로벌 확장 & SEO")
    st.markdown(
        """
    Streamlit 기반 MVP는 **데모/해커톤에는 최고**지만, 검색 엔진이 잘 크롤링하는 구조(SSR/정적 페이지)로 만들기는 제한이 있습니다.

    그래서 StayPick의 글로벌/SEO는 보통 이렇게 갑니다:
    1) **앱(StayPick)**: 실시간 피드/요약/재가공(인터랙티브)
    2) **SEO 퍼블리싱(정적 페이지)**: 요약/재가공 결과를 HTML로 내보내서(정적) 검색 유입을 받기

    아래는 MVP에서도 바로 가능한 **SEO HTML Export** 기능입니다.
    """
    )

    st.markdown("### 🔗 언어 고정 링크")
    st.caption("배포 후에는 URL에 `?lang=en`처럼 붙이면 해당 언어로 바로 열리게 할 수 있어요.")
    st.code("/ ?lang=ko   |   / ?lang=en   |   / ?lang=ja   |   / ?lang=es")

    st.markdown("### 🗺️ 지역별 대표 언어(기본값 예시)")
    st.markdown(
        """
    - **북미/오세아니아**: English
    - **중남미**: Español / Português
    - **유럽**: English(공용) + FR/DE/ES(확장)
    - **중동/북아프리카**: العربية
    - **아프리카(사하라 이남)**: English / Français / Kiswahili
    - **동아시아**: 中文 / 日本語 / 한국어
    - **동남아**: English + ID/TH/VI(확장)
    - **남아시아**: हिन्दी + English
    """
    )
    st.caption("실서비스에서는 보통 IP Geo(Cloudflare/Vercel) + 브라우저 언어(Accept-Language)로 기본 언어를 결정하고, 항상 수동 변경을 허용합니다.")

    st.divider()
    st.markdown("### 📄 SEO HTML 패키지로 내보내기")
    selected_list: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
    if not selected_list:
        st.info("먼저 피드에서 글을 '저장'한 뒤, 여기서 HTML로 내보낼 수 있어요.")
    else:
        export_lang = st.selectbox(
            "Export language",
            options=["auto", "ko", "en", "ja", "es"],
            format_func=lambda x: {"auto": "Auto (UI)", "ko": "한국어", "en": "English", "ja": "日本語", "es": "Español"}.get(x, x),
            index=0,
        )
        lang_now = st.session_state.get("ui_lang", "ko")
        lang_export = lang_now if export_lang == "auto" else normalize_lang(export_lang)

        if st.button("📦 저장 목록을 HTML ZIP으로 내보내기", type="primary"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for s in selected_list:
                    title_for_export = (s.get("localized_title") or s.get("title") or "staypick").strip()
                    desc_for_export = (s.get("one_liner") or s.get("summary") or "").strip()[:180]
                    url = (s.get("url") or "").strip()
                    body_html = "".join(
                        [
                            f"<h2>One-liner</h2><p>{html.escape((s.get('one_liner') or '').strip())}</p>",
                            f"<h2>Summary</h2><p>{html.escape((s.get('summary') or '').strip())}</p>",
                            "<h2>Key points</h2><ul>" + "".join([f"<li>{html.escape(str(x))}</li>" for x in (s.get('key_points') or [])]) + "</ul>",
                            "<h2>Tags</h2><p>" + ", ".join([html.escape(str(x)) for x in (s.get('tags') or [])]) + "</p>",
                            f"<h2>Sources</h2><p><a href='{html.escape(url)}'>{html.escape(url)}</a></p>",
                        ]
                    )
                    html_text = render_html(
                        SEOPage(
                            title=title_for_export,
                            description=desc_for_export,
                            lang=lang_export,
                            canonical_url=url,
                            body_html=body_html,
                        )
                    )
                    fn = f"{slugify(title_for_export)}_{lang_export}.html"
                    z.writestr(fn, html_text)

            buf.seek(0)
            st.download_button(
                "⬇️ ZIP 다운로드",
                data=buf.getvalue(),
                file_name=f"staypick_seo_export_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip",
            )
            st.success("내보내기 준비 완료! (이 ZIP을 정적 호스팅에 올리면 SEO 페이지가 됩니다)")


    # ---------------------------
    # Programmatic SEO export (/{lang}/{country}/{category}/)
    # ---------------------------
    st.divider()
    st.markdown("### 🚀 Programmatic SEO 패키지 (/{lang}/{country}/{category}/)")
    st.caption(
        "카테고리별 Top N을 **정적 HTML 폴더 구조**로 내보냅니다. "
        "예: /ko/kr/game/ · /en/us/finance/ · /ja/jp/travel/"
    )

    df_scored = st.session_state.get("df_scored", pd.DataFrame())
    if df_scored is None or df_scored.empty:
        st.info("데이터가 없습니다. 먼저 ‘데이터(운영자)’ 탭에서 CSV/URL을 넣어주세요.")
    else:
        colP1, colP2, colP3 = st.columns([1, 1, 1], gap="medium")
        with colP1:
            export_lang = st.selectbox("페이지 언어(lang)", options=["ko", "en", "ja", "es"], index=["ko", "en", "ja", "es"].index(st.session_state.get("ui_lang", "ko")))
        with colP2:
            country_code = st.selectbox("국가 코드(country)", options=["kr", "us", "jp", "es", "mx", "br", "id", "vn", "th", "fr", "de"], index=0)
        with colP3:
            top_k = st.slider("카테고리별 Top N", min_value=3, max_value=20, value=10, step=1)

        # Audience tuning for summaries/hooks on SEO pages
        age_for_seo = st.selectbox(
            t("age_group") + " (SEO용)",
            options=["general", "elem", "mid", "high", "uni", "20s", "30s"],
            format_func=lambda x: {
                "general": t("age_general"),
                "elem": t("age_elem"),
                "mid": t("age_mid"),
                "high": t("age_high"),
                "uni": t("age_uni"),
                "20s": t("age_20s"),
                "30s": t("age_30s"),
            }.get(x, x),
            index=["general", "elem", "mid", "high", "uni", "20s", "30s"].index("general"),
        )

        base_url = st.text_input("Base URL(선택, sitemap용)", value="", placeholder="예: https://staypick.yourdomain.com")

        categories_all = sorted([c for c in df_scored.get("category", pd.Series(dtype=str)).dropna().unique().tolist() if str(c).strip()]) or ["전체"]
        default_cats = categories_all[: min(len(categories_all), 6)]
        cats_sel = st.multiselect("내보낼 카테고리", options=categories_all, default=default_cats)

        use_ai = st.checkbox("AI 요약/훅 포함(권장)", value=True, help="체류/클릭을 돕는 제목/훅/요약을 함께 넣습니다. (OpenAI API 사용)")
        if use_ai and not api_key:
            st.warning("AI 요약을 포함하려면 OPENAI_API_KEY가 필요합니다. (환경변수 또는 사이드바 입력)")

        # Simple mapping to make pretty slugs for common Korean categories
        CAT_SLUG = {
            "게임": "game",
            "연애/썰": "love",
            "연애": "love",
            "썰": "story",
            "여행": "travel",
            "재테크": "finance",
            "생활꿀팁": "lifehacks",
            "생활": "life",
            "테크": "tech",
            "테크트렌드": "tech",
            "전체": "all",
        }

        COUNTRY_NAME = {
            "kr": {"ko": "한국", "en": "Korea", "ja": "韓国", "es": "Corea"},
            "us": {"ko": "미국", "en": "United States", "ja": "アメリカ", "es": "EE. UU."},
            "jp": {"ko": "일본", "en": "Japan", "ja": "日本", "es": "Japón"},
            "es": {"ko": "스페인", "en": "Spain", "ja": "スペイン", "es": "España"},
            "mx": {"ko": "멕시코", "en": "Mexico", "ja": "メキシコ", "es": "México"},
            "br": {"ko": "브라질", "en": "Brazil", "ja": "ブラジル", "es": "Brasil"},
            "id": {"ko": "인도네시아", "en": "Indonesia", "ja": "インドネシア", "es": "Indonesia"},
            "vn": {"ko": "베트남", "en": "Vietnam", "ja": "ベトナム", "es": "Vietnam"},
            "th": {"ko": "태국", "en": "Thailand", "ja": "タイ", "es": "Tailandia"},
            "fr": {"ko": "프랑스", "en": "France", "ja": "フランス", "es": "Francia"},
            "de": {"ko": "독일", "en": "Germany", "ja": "ドイツ", "es": "Alemania"},
        }

        def _country_name(code: str, lang_code: str) -> str:
            return COUNTRY_NAME.get(code, {}).get(lang_code, code.upper())

        def _cat_slug(cat: str) -> str:
            c = (cat or "").strip()
            if c in CAT_SLUG:
                return CAT_SLUG[c]
            return slugify(c)

        TITLE_TMPL = {
            "ko": lambda cn, cat, n: f"오늘 {cn}에서 오래 읽힌 {cat} TOP{n}",
            "en": lambda cn, cat, n: f"Today's Top {n} {cat} in {cn} (by dwell time)",
            "ja": lambda cn, cat, n: f"今日 {cn} で長く読まれた {cat} TOP{n}",
            "es": lambda cn, cat, n: f"Top {n} de {cat} más leídos hoy en {cn}",
        }
        DESC_TMPL = {
            "ko": lambda cn, cat: f"{cn}에서 체류시간/방문이 높았던 {cat} 글을 3초 요약으로 정리했습니다.",
            "en": lambda cn, cat: f"We summarize the {cat} posts people spent the most time on in {cn}.",
            "ja": lambda cn, cat: f"{cn}で滞在時間が長かった{cat}投稿を3秒で要約します。",
            "es": lambda cn, cat: f"Resumimos en 3s los posts de {cat} con mayor tiempo de lectura en {cn}.",
        }

        if st.button(
            "📦 Programmatic SEO ZIP 생성",
            type="primary",
            key="btn_progseo",
            disabled=not programmatic_seo_enabled,
        ):
            # Build top-k per category
            topk_df = topk_per_category(df_scored, top_k=int(top_k))
            if cats_sel:
                topk_df = topk_df[topk_df["category"].isin(cats_sel)]
            rows = topk_df.to_dict(orient="records")

            # Group by category
            by_cat: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows:
                by_cat.setdefault(r.get("category", "전체"), []).append(r)

            # Local cache for summaries during this export
            export_cache: Dict[str, Dict[str, Any]] = {}

            # Prepare AI if needed
            ai = None
            if use_ai:
                try:
                    ai = ensure_ai()
                except Exception as e:
                    st.error(str(e))
                    use_ai = False

            mem = io.BytesIO()
            z = zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED)

            # Locale landing page
            lang_code = export_lang
            cn = _country_name(country_code, lang_code)

            loc_index_path = f"{lang_code}/{country_code}/index.html"
            cat_links = []
            for cat in sorted(by_cat.keys()):
                cat_slug = _cat_slug(cat)
                cat_links.append((cat, f"./{cat_slug}/index.html"))
            body_links = "<ul>" + "".join([f'<li><a href="{html.escape(href)}">{html.escape(cat)}</a></li>' for cat, href in cat_links]) + "</ul>"
            index_page = SEOPage(
                title=f"StayPick · {cn}",
                description=f"{cn} 카테고리별 TOP 콘텐츠를 3초 요약으로 제공합니다.",
                lang=lang_code,
                canonical_url=(base_url.rstrip("/") + "/" + loc_index_path) if base_url else "",
                body_html=(
                    f"<h1>StayPick · {html.escape(cn)}</h1>"
                    f"<p>카테고리별 TOP{int(top_k)} · 3초 요약 + 핵심 포인트</p>"
                    f"{body_links}"
                    f"<p style='opacity:0.65;font-size:12px'>Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"
                ),
            )
            z.writestr(loc_index_path, render_html(index_page))

            # Category pages
            sitemap_urls = []
            if base_url:
                sitemap_urls.append(base_url.rstrip("/") + "/" + loc_index_path)

            total_items = sum(len(v) for v in by_cat.values())
            done = 0
            prog = st.progress(0, text="HTML 생성 중...")

            for cat, items in by_cat.items():
                cat_slug = _cat_slug(cat)
                page_path = f"{lang_code}/{country_code}/{cat_slug}/index.html"
                h1 = TITLE_TMPL.get(lang_code, TITLE_TMPL["en"])(cn, cat, int(top_k))
                desc = DESC_TMPL.get(lang_code, DESC_TMPL["en"])(cn, cat)

                # Build item list HTML
                parts = [f"<h1>{html.escape(h1)}</h1>", f"<p>{html.escape(desc)}</p>"]
                parts.append("<hr/>")

                for r in items:
                    url = r.get("url", "")
                    src_title = (r.get("title") or "").strip() or url
                    content_from_csv = (r.get("content") or "").strip()
                    metrics = {
                        "visits": float(r.get("visits", 0) or 0),
                        "avg_dwell_sec": float(r.get("avg_dwell_sec", 0) or 0),
                        "engagement_score": float(r.get("engagement_score", 0) or 0),
                        "comment_count": float(r.get("comment_count", 0) or 0),
                        "published_at": str(r.get("published_at", "") or ""),
                    }

                    s = None
                    if use_ai and ai and url:
                        if url in export_cache:
                            s = export_cache[url]
                        else:
                            try:
                                if content_from_csv:
                                    page_title, text0 = src_title, content_from_csv
                                else:
                                    fetched_title, text0 = cached_fetch(url)
                                    page_title = fetched_title or src_title
                                s = ai.summarize(
                                    url=url,
                                    title=page_title,
                                    content=text0,
                                    metrics=metrics,
                                    language=lang_code,
                                    age_group=age_for_seo,
                                )
                                export_cache[url] = s
                            except Exception:
                                s = None

                    display_title = (s.get("localized_title") or s.get("title")) if s else src_title
                    hook = (s.get("hook") or "") if s else ""
                    one = (s.get("one_liner") or "") if s else snippet_from_content(content_from_csv, 140)
                    kps = s.get("key_points") if s else []
                    tags = s.get("tags") if s else []

                    parts.append(f"<h2><a href='{html.escape(url)}' target='_blank' rel='noopener'>{html.escape(display_title)}</a></h2>")
                    if hook:
                        parts.append(f"<p><strong>{html.escape(hook)}</strong></p>")
                    if one:
                        parts.append(f"<p>{html.escape(one)}</p>")
                    if kps:
                        parts.append("<ul>" + "".join([f"<li>{html.escape(str(k))}</li>" for k in kps[:3]]) + "</ul>")
                    if tags:
                        parts.append(
                            "<p style='opacity:0.7;font-size:12px'>"
                            + " · ".join([html.escape(str(tg)) for tg in tags[:6]])
                            + "</p>"
                        )
                    parts.append("<hr/>")

                    done += 1
                    if total_items:
                        prog.progress(min(done / total_items, 1.0), text="HTML 생성 중...")

                page = SEOPage(
                    title=h1,
                    description=desc,
                    lang=lang_code,
                    canonical_url=(base_url.rstrip("/") + "/" + page_path) if base_url else "",
                    body_html="\n".join(parts),
                )
                z.writestr(page_path, render_html(page))
                if base_url:
                    sitemap_urls.append(base_url.rstrip("/") + "/" + page_path)

            prog.empty()

            # Optional: sitemap.xml
            if base_url and sitemap_urls:
                urls_xml = "".join([f"<url><loc>{html.escape(u)}</loc></url>" for u in sitemap_urls])
                sitemap = "<?xml version='1.0' encoding='UTF-8'?>\n" + "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" + urls_xml + "</urlset>"
                z.writestr("sitemap.xml", sitemap)

            # robots.txt (basic)
            if base_url:
                robots = "User-agent: *\nAllow: /\nSitemap: " + base_url.rstrip("/") + "/sitemap.xml\n"
                z.writestr("robots.txt", robots)

            z.close()
            mem.seek(0)

            st.download_button(
                "Programmatic SEO ZIP 다운로드",
                data=mem.getvalue(),
                file_name=f"staypick_programmatic_seo_{export_lang}_{country_code}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                mime="application/zip",
            )
            st.success("생성 완료! ZIP을 정적 호스팅에 업로드하면 /{lang}/{country}/{category}/ 구조로 바로 서비스할 수 있습니다.")
        if not programmatic_seo_enabled:
            st.info("Programmatic SEO export is available on Pro plan.")
