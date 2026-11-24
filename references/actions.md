# GitHub Actions

The workflow uses the action-as-cpu fan-out pattern. Each runner encodes one PDF. A final job checks complete page sequences, duration and video/audio streams, and optionally publishes one Release.

## Stage a request

Keep this workflow and its scripts in the compute repo on its default branch so it can be dispatched. Stage PDFs and any note sidecars in a separate authorized source repo. Pin the source to a full commit SHA. For a private source, grant a temporary read-only deploy key and set its private counterpart as `PDF_VIDEO_INPUT_KEY` in the compute repo. GitHub Actions artifacts share the visibility of the compute repo. Use a private compute repo if either the intermediate films or final films require private access.

Commit a request configuration to the compute repo. The configuration contains file paths and display metadata. Omit `release_tag` to deliver through workflow artifacts only.

```json
{
  "input_repository": "owner/private-pdf-inputs",
  "input_ref": "0123456789abcdef0123456789abcdef01234567",
  "voice": "zh-TW-HsiaoChenNeural",
  "release_tag": "pdf-video-reading-2026",
  "documents": [
    {
      "id": "reference-guide",
      "title": "文件導讀",
      "version": "2026 edition",
      "pdf": "pdfs/reference-guide.pdf",
      "notes": "notes/reference-guide.json"
    }
  ]
}
```

A notes file is a JSON array. The page index starts at 1. Focus rectangles use normalized left, top, right and bottom in the visual orientation of the PDF. When there is no authored focus list, the renderer derives a geometric reading order from the page and uses the supplied summary, or a neutral reading prompt. Scanned pages without text are swept by quadrant.

```json
[
  {
    "page": 3,
    "ref": "A-1",
    "heading": "對照條件與結果",
    "subheading": "The two decision branches",
    "summary": "先定位入口，再對照各分支的條件。",
    "spoken_title": "決策流程",
    "focuses": [
      {"rect": [0.08, 0.20, 0.47, 0.70], "caption": "這一區列出進入流程的條件。"},
      {"rect": [0.44, 0.19, 0.96, 0.86], "caption": "順著箭頭核對處置與註腳。"}
    ]
  }
]
```

## Execute and collect

```sh
# Synthetic two-page demo. It produces an Action artifact.
gh workflow run pdf-video.yml -f demo=true

# Full batch. Up to 20 documents per request.
gh workflow run pdf-video.yml -f demo=false -f request=requests/render.json
gh run watch RUN_ID --exit-status
gh run download RUN_ID --pattern 'pdf-video-*' --dir downloaded
# If a release was requested:
gh release download TAG --dir downloaded-release
python3 scripts/verify.py downloaded-release requests/render.json
```

Each timeline gives the start and end time for each physical page and identifies which pages have title narration. Stream and coverage checks do not verify editorial completeness. Review the sample and spot-check dense pages, reference pages and the return-to-overview transitions, then review the source coverage claimed in the delivery. Split inputs into more runs if a file would approach GitHub's per-asset limits.
