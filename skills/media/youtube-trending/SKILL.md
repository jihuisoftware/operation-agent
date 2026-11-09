---
name: youtube-trending
description: Find and rank popular YouTube videos by region and period.
version: 1.0.0
author: dm, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [YouTube, video, trending, discovery]
    category: media
    related_skills: [youtube-content]
---

# YouTube Trending Videos Skill

Find current popular YouTube videos and present a sourced, time-stamped shortlist. “Popular” can mean currently trending, most viewed recently, or most viewed of all time; use the user's wording and clarify the ranking basis in the result.

## When to Use

Use when the user asks for YouTube trending, hottest, popular, or most-viewed videos, either generally or for a topic, region, or time period. Use `youtube-content` when they want a transcript or summary of a particular video.

## Prerequisites

Use available web discovery tools such as `web_search`, `web_extract`, or `browser`; do not assume a YouTube API key or a particular third-party CLI is configured. Prefer YouTube pages or other sources that link directly to the video. If a dedicated YouTube ranking source is unavailable, search the web and describe the result as a sourced shortlist rather than a definitive platform-wide ranking.

## How to Run

1. Resolve the ranking basis from the request. “Trending/hot right now” means currently gaining attention; “most viewed this week/month/year” means views within that period if a source supports that measure; “most viewed ever” means lifetime views. Do not mix these lists.
2. Use the requested region, topic, language, and count. If region is omitted, use the user's apparent locale when clear; otherwise say which region or worldwide sources you used. If period is omitted for “trending,” treat it as current and record the lookup date.
3. Search current sources, opening result pages as needed to confirm the video identity, publication date, and available view count. Favor YouTube's own pages and reputable chart sources. Search results alone may be stale or personalized; do not present them as a complete official ranking.
4. Rank only by the metric requested and only when comparable data is available. If the source gives total views rather than period views, label them as lifetime views. Do not infer view velocity from total views.
5. Present a compact numbered list with title, creator/channel, direct YouTube link, view count (when visible), publish date or age, and why it qualifies. Include region, ranking basis, and “checked on” date. Attach source links near the claims they support.
6. State limits plainly when sources disagree, omit counts, personalize results, or cannot establish a complete ranking. Do not invent unavailable metrics or imply an official global list.

## Quick Reference

- Ask one short clarification only if the ranking basis materially changes the answer and cannot be inferred.
- “Trending” is not interchangeable with “most viewed.”
- “Most viewed recently” requires period-specific view data; lifetime counts are not a substitute.
- For a broad request, return a useful shortlist and identify its geographic and source scope.
