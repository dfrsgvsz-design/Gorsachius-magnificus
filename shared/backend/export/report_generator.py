"""
HTML report generator for biodiversity acoustic survey outputs.

Produces a browser-friendly report with:
- Species list with confidence scores
- Alpha diversity indices
- Summary statistics
- Embedded chart images
"""

import base64
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt


def _setup_chinese_font():
    """Try to use a font that supports Chinese characters."""
    for name in [
        "SimHei",
        "Microsoft YaHei",
        "WenQuanYi Micro Hei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
    ]:
        try:
            prop = fm.FontProperties(family=name)
            if prop.get_name() != name:
                continue
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return True
        except Exception:
            continue
    return False


_setup_chinese_font()


def generate_species_chart(detections, max_species=15):
    """Generate a horizontal bar chart of detected species."""
    if not detections:
        return None

    species_conf = {}
    for detection in detections:
        name = detection.get("species_chinese") or detection.get(
            "species_scientific", "Unknown"
        )
        confidence = detection.get("confidence", 0)
        if name not in species_conf or confidence > species_conf[name]:
            species_conf[name] = confidence

    sorted_species = sorted(
        species_conf.items(), key=lambda item: item[1], reverse=True
    )[:max_species]
    names = [item[0] for item in sorted_species]
    confidences = [item[1] for item in sorted_species]

    fig, ax = plt.subplots(figsize=(8, max(3, len(names) * 0.4)))
    colors = [
        "#10b981" if value > 0.5 else "#f59e0b" if value > 0.3 else "#ef4444"
        for value in confidences
    ]
    ax.barh(range(len(names)), confidences, color=colors, height=0.6)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Confidence", fontsize=10)
    ax.set_title("Species Detection Results", fontsize=12, fontweight="bold")
    ax.set_xlim(0, 1.0)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


def generate_diversity_chart(diversity_data):
    """Generate a chart for core alpha-diversity metrics."""
    if not diversity_data:
        return None

    metrics = {
        "Shannon H'": diversity_data.get("shannon_h", 0),
        "Simpson D": diversity_data.get("simpson_d", 0),
        "Evenness": diversity_data.get("evenness", 0),
    }

    fig, ax = plt.subplots(figsize=(6, 4))
    colors = ["#06b6d4", "#0f766e", "#10b981"]
    bars = ax.bar(metrics.keys(), metrics.values(), color=colors, width=0.5)
    for bar, value in zip(bars, metrics.values()):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    ax.set_title("Alpha Diversity Indices", fontsize=12, fontweight="bold")
    ax.set_ylim(0, max(metrics.values()) * 1.3 + 0.1)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


def generate_report_html(
    analysis_result,
    site_name="Unknown Site",
    author="Biodiversity Survey Platform V7 Acoustic Engine",
):
    """Generate an HTML report that can be viewed in a browser or printed to PDF."""
    detections = analysis_result.get("detections", [])
    diversity = analysis_result.get("diversity_summary", {})

    total_species = len(
        {
            item["species_scientific"]
            for item in detections
            if item.get("species_scientific")
        }
    )
    total_detections = len(detections)
    reliable_detections = sum(1 for item in detections if item.get("reliable"))

    species_chart_png = generate_species_chart(detections)
    diversity_chart_png = generate_diversity_chart(diversity)
    species_chart_b64 = (
        base64.b64encode(species_chart_png).decode() if species_chart_png else ""
    )
    diversity_chart_b64 = (
        base64.b64encode(diversity_chart_png).decode() if diversity_chart_png else ""
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []
    seen = set()
    for detection in sorted(
        detections, key=lambda item: item.get("confidence", 0), reverse=True
    ):
        scientific_name = detection.get("species_scientific", "")
        if scientific_name in seen:
            continue
        seen.add(scientific_name)
        confidence = detection.get("confidence", 0)
        confidence_color = (
            "#10b981"
            if confidence > 0.5
            else "#f59e0b" if confidence > 0.3 else "#ef4444"
        )
        reliable = "Yes" if detection.get("reliable") else "No"
        rows.append(f"""<tr>
            <td>{detection.get('species_chinese', '')}</td>
            <td><em>{scientific_name}</em></td>
            <td>{detection.get('species_english', '')}</td>
            <td style="color:{confidence_color};font-weight:bold">{confidence:.1%}</td>
            <td>{reliable}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Biodiversity Acoustic Survey Report - {site_name}</title>
<style>
  body {{ font-family: 'Microsoft YaHei', 'SimHei', sans-serif; margin: 40px; color: #1f2937; line-height: 1.6; }}
  h1 {{ color: #0f766e; border-bottom: 3px solid #14b8a6; padding-bottom: 10px; }}
  h2 {{ color: #155e75; margin-top: 30px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 14px; }}
  th, td {{ border: 1px solid #d1d5db; padding: 8px 12px; text-align: left; }}
  th {{ background: #f0fdfa; color: #115e59; font-weight: bold; }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
  .stat-card {{ background: #f0fdfa; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #99f6e4; }}
  .stat-card .value {{ font-size: 24px; font-weight: bold; color: #115e59; }}
  .stat-card .label {{ font-size: 12px; color: #6b7280; margin-top: 5px; }}
  .chart {{ text-align: center; margin: 20px 0; }}
  .chart img {{ max-width: 100%; border: 1px solid #e5e7eb; border-radius: 8px; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #d1d5db; font-size: 12px; color: #6b7280; text-align: center; }}
  .meta {{ background: #f8fafc; padding: 15px; border-radius: 8px; font-size: 13px; margin: 15px 0; }}
</style>
</head>
<body>

<h1>Biodiversity Acoustic Survey Report</h1>

<div class="meta">
  <strong>Site:</strong> {site_name} &nbsp;|&nbsp;
  <strong>Generated:</strong> {now} &nbsp;|&nbsp;
  <strong>Analysis Engine:</strong> {author}
</div>

<div class="stat-grid">
  <div class="stat-card"><div class="value">{total_species}</div><div class="label">Unique Species</div></div>
  <div class="stat-card"><div class="value">{total_detections}</div><div class="label">Total Detections</div></div>
  <div class="stat-card"><div class="value">{reliable_detections}</div><div class="label">Reliable Detections</div></div>
  <div class="stat-card"><div class="value">{diversity.get('shannon_h', 0):.3f}</div><div class="label">Shannon H'</div></div>
</div>

<h2>Species Detections</h2>

{f'<div class="chart"><img src="data:image/png;base64,{species_chart_b64}" alt="Species Chart" /></div>' if species_chart_b64 else ''}

<table>
  <tr><th>Chinese Name</th><th>Scientific Name</th><th>English Name</th><th>Confidence</th><th>Reliable</th></tr>
  {''.join(rows)}
</table>

<h2>Alpha Diversity Metrics</h2>

{f'<div class="chart"><img src="data:image/png;base64,{diversity_chart_b64}" alt="Diversity Chart" /></div>' if diversity_chart_b64 else ''}

<table>
  <tr><th>Metric</th><th>Value</th><th>Description</th></tr>
  <tr><td>Shannon H'</td><td>{diversity.get('shannon_h', 0):.4f}</td><td>Higher values indicate greater diversity.</td></tr>
  <tr><td>Simpson D</td><td>{diversity.get('simpson_d', 0):.4f}</td><td>Probability that two sampled individuals are different species.</td></tr>
  <tr><td>Chao1</td><td>{diversity.get('chao1', 0):.1f}</td><td>Estimated true species richness.</td></tr>
  <tr><td>Evenness</td><td>{diversity.get('evenness', 0):.4f}</td><td>How evenly detections are distributed across species.</td></tr>
  <tr><td>Observed Richness</td><td>{diversity.get('observed_richness', total_species)}</td><td>Number of species detected.</td></tr>
</table>

<div class="footer">
  <p>Generated by the Biodiversity Survey Platform acoustic analysis module.</p>
  <p>Species-based biodiversity reporting informed by the Sugai et al. (2026) framing used in this project.</p>
</div>

</body>
</html>"""
    return html
