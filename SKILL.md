---
name: pdf-to-video-skill
description: Turn PDFs into one motion walkthrough MP4 each, using the original pages, white de-emphasis, overview-to-focus-to-overview camera moves, short captions, title-only Edge TTS and synthesized cues. Use when the user asks for a video walkthrough or animated guide based on PDF pages, especially a batch rendered through GitHub Actions.
---

# PDF to video

Render each input PDF into its own video, including its front matter, main content and references. Preserve physical page numbering and the source page as the visual layer. Keep the sequence **whole page → focal elements → whole page** before every page change. Use dark caption text on white and place notes outside the document image.

- Check the source edition from the PDF itself. Use notes tied to that edition and physical page number.
- For an explanatory walkthrough, author concise page summaries and focal captions anchored to bounding boxes. For flowcharts, follow arrows and preserve alternative branches and footnotes. Choose neutral reading prompts when the evidence does not support an interpretation.
- Speak the document title and any authored section titles with Edge TTS. Leave paragraphs, tables and focal captions on screen. Edge TTS receives title text only.
- Build and verify a synthetic or user-authorized short sample before a large batch when callout or timing choices are uncertain.
- Use the included GitHub Actions workflow for cloud encoding. Match output visibility to the user's authorization, including intermediate Actions artifacts. Keep protected inputs in a separate private repo with a read-only deploy key.

Read [the GitHub Actions procedure and data formats](references/actions.md) to configure a run. Wait for every shard, verify one MP4 and one complete timeline per input, download requested assets, and remove temporary releases only when requested and after verifying the downloads.
