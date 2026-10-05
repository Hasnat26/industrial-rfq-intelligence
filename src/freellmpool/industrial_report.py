"""Recruiter-facing rendering for the industrial RFQ workflow."""

from __future__ import annotations

from typing import Any


def render_engineering_report(report: dict[str, Any], title: str = "Industrial RFQ Engineering Review") -> str:
    """Render a concise Markdown report without ranking vendors or making procurement decisions."""
    summary = report["summary"]
    lines = [
        f"# {title}",
        "",
        "## Executive summary",
        "",
        f"- Requirements checked: **{summary['requirements_checked']}**",
        f"- Vendors checked: **{summary['vendors_checked']}**",
        f"- Deviations: **{summary['deviations']}**",
        f"- Unverified fields: **{summary['unverified_fields']}**",
        f"- Claims requiring review: **{summary['claims_requiring_review']}**",
        "",
        "This report is an evidence-aware engineering review. It does not select a supplier or make an autonomous procurement decision.",
        "",
        "## Technical compliance matrix",
        "",
        "| Requirement | Vendor | Parameter | Required | Offered | Status | Evidence |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["matrix"]:
        lines.append(
            f"| {row['requirement']} | {row['vendor']} | {row['parameter']} | "
            f"{row['required']} | {row['offered']} | {row['status']} | {row['evidence']} |"
        )

    summary_data = report.get("engineering_decision_summary", {})
    if summary_data:
        lines += [
            "",
            "## Auditable engineering decision summary",
            "",
            f"- Technical disposition: **{summary_data['status']}**",
            "",
        ]
        for basis in summary_data["decision_basis"]:
            lines.append(f"- {basis}")
        lines += [
            "",
            "| Vendor | Disposition | Technical score | Evidence coverage | Compliant | Deviations | Major | Conflicts | Missing evidence |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in summary_data["vendor_profiles"]:
            lines.append(
                f"| {row['vendor']} | {row['disposition']} | {row['technical_score']:.2f} | "
                f"{row['evidence_coverage_pct']:.2f}% | {row['compliant_count']} | "
                f"{row['deviation_count']} | {row['major_deviation_count']} | "
                f"{row['conflict_count']} | {row['missing_evidence_count']} |"
            )
        if summary_data["review_actions"]:
            lines += ["", "### Required engineering review actions", ""]
            for action in summary_data["review_actions"]:
                lines.append(f"- {action}")

    commercial = report.get("commercial_comparison", [])
    if commercial:
        lines += [
            "",
            "## Commercial information",
            "",
            "| Vendor | Price | Currency | Lead time | Warranty | Payment terms | Claim status | Evidence |",
            "|---|---:|---|---|---|---|---|---|",
        ]
        for row in commercial:
            lines.append(
                f"| {row['vendor']} | {row['price']} | {row['currency']} | {row['lead_time']} | "
                f"{row['warranty']} | {row['payment_terms']} | {row['claim_status']} | {row['evidence']} |"
            )

    risk_review = report.get("commercial_risk_review", [])
    if risk_review:
        lines += [
            "",
            "## Commercial risk review",
            "",
            "These are deterministic review flags, not supplier rankings or selection criteria.",
            "",
            "| Vendor | Price | Currency | Lead time (weeks) | Warranty (months) | Claim status | Flags | Review required |",
            "|---|---:|---|---:|---:|---|---|---|",
        ]
        for row in risk_review:
            flags = ", ".join(row["flags"]) if row["flags"] else "None"
            lines.append(
                f"| {row['vendor']} | {row['price']} | {row['currency']} | "
                f"{row['lead_time_weeks']} | {row['warranty_months']} | "
                f"{row['claim_status']} | {flags} | "
                f"{'YES' if row['review_required'] else 'NO'} |"
            )

    lines += ["", "## Evidence register", "", "| Source | Vendor | Field | Value | Claim status | Review | Evidence | Source file | Page | Section | Table | Cell |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in report["evidence_register"]:
        lines.append(
            f"| {row['source_type']} | {row['vendor']} | {row['field']} | {row['value']} | "
            f"{row['claim_status']} | {row['review_required']} | {row['evidence']} | {row['source']} | {row['page']} | {row['section']} | {row['table']} | {row['cell']} |"
        )

    actions = report.get("review_actions", [])
    lines += ["", "## Engineer review actions", ""]
    if actions:
        for row in actions:
            lines.append(
                f"- **{row['vendor']} / {row['parameter']}**: offered `{row['offered']}`, "
                f"required `{row['required']}`. Verify against source evidence: {row['evidence']}."
            )
    else:
        lines.append("- No technical deviations require review in this dataset.")

    lines += [
        "",
        "## Controls and limitations",
        "",
        "- LLM output is treated as extraction assistance, not as the compliance decision.",
        "- Compliance status is calculated by the deterministic comparison engine.",
        "- Missing or unsupported claims remain reviewable rather than being silently inferred.",
        "- Commercial fields are presented for review; no automatic winner is selected.",
        "- Commercial risk flags are deterministic exception indicators; they are not supplier scores.",
        "- Evidence provenance identifies the source location when structured provenance is available.",
        "",
    ]
    return "\n".join(lines)


__all__ = ["render_engineering_report"]
