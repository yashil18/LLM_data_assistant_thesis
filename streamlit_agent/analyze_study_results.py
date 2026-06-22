"""Export study results from interactions.db to an Excel analysis workbook.

Run from the project root:
    python streamlit_agent/analyze_study_results.py
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from study_storage import read_study_table


TRUST_ITEMS = {
    "TBB1": "trust_benevolence",
    "TBB2": "trust_benevolence",
    "TBB3": "trust_benevolence",
    "TBI1": "trust_integrity",
    "TBI2": "trust_integrity",
    "TBI3": "trust_integrity",
    "TBI4": "trust_integrity",
    "TBC1": "trust_competence",
    "TBC2": "trust_competence",
    "TBC3": "trust_competence",
    "TBC4": "trust_competence",
}

SATISFACTION_ITEMS = {"SAT1", "SAT2", "SAT3", "SAT4"}
GUIDED_EXPLORATION_ITEMS = {"GE1", "GE2", "GE3", "GE4", "GE5"}

PRE_ITEMS = {
    "AGE_GROUP": "age_group",
    "GENDER": "gender",
    "EDUCATION": "education",
    "AI_EXPERIENCE": "ai_experience",
    "DATA_EXPERIENCE": "data_experience",
    "SQL_EXPERIENCE": "sql_experience",
    "BUSINESS_EXPERIENCE": "business_experience",
}

COMMENT_QUESTION_LABELS = {
    "OPEN_TRUST": "Trust or distrust reason",
    "OPEN_EXPLANATION_FEATURE": "Explanation feature that made a difference",
    "OPEN_GUIDED_EXPLORATION": "Guided exploration experience",
    "OPEN_IMPROVEMENT": "Improvement suggestion",
}


def normalize_version(value):
    text = str(value or "").strip().lower()
    if "kg" in text or "version b" in text:
        return "kg_enhanced"
    if "baseline" in text or "normal" in text or "version a" in text:
        return "baseline"
    return text or "unknown"


def safe_read_sql(connection, table_name):
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if not exists:
        return pd.DataFrame()
    return pd.read_sql_query(f"SELECT * FROM {table_name}", connection)


def _mean(values):
    values = [float(value) for value in values if pd.notna(value)]
    if not values:
        return math.nan
    return sum(values) / len(values)


def _sample_sd(values):
    values = [float(value) for value in values if pd.notna(value)]
    if len(values) < 2:
        return math.nan
    mean_value = _mean(values)
    return math.sqrt(sum((value - mean_value) ** 2 for value in values) / (len(values) - 1))


def _betacf(a, b, x, max_iter=200, eps=3e-12):
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d

    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _regularized_incomplete_beta(x, a, b):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    ln_beta_term = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    bt = math.exp(ln_beta_term)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t_statistic, degrees_of_freedom):
    if degrees_of_freedom <= 0 or pd.isna(t_statistic):
        return math.nan
    x = degrees_of_freedom / (degrees_of_freedom + t_statistic * t_statistic)
    beta_value = _regularized_incomplete_beta(x, degrees_of_freedom / 2.0, 0.5)
    if t_statistic >= 0:
        return 1.0 - 0.5 * beta_value
    return 0.5 * beta_value


def two_tailed_t_p_value(t_statistic, degrees_of_freedom):
    if degrees_of_freedom <= 0 or pd.isna(t_statistic):
        return math.nan
    tail = 1.0 - student_t_cdf(abs(t_statistic), degrees_of_freedom)
    return min(1.0, max(0.0, 2.0 * tail))


def paired_t_test(baseline_values, kg_values):
    paired = pd.DataFrame({"baseline": baseline_values, "kg_enhanced": kg_values}).dropna()
    n = len(paired)
    if n < 2:
        return {
            "test_used": "paired t-test",
            "n_pairs": n,
            "t_statistic": math.nan,
            "degrees_of_freedom": math.nan,
            "p_value": math.nan,
            "effect_size_d": math.nan,
        }

    differences = paired["kg_enhanced"] - paired["baseline"]
    mean_difference = differences.mean()
    sd_difference = differences.std(ddof=1)
    if sd_difference == 0 or pd.isna(sd_difference):
        t_statistic = math.inf if mean_difference != 0 else 0.0
        p_value = 0.0 if mean_difference != 0 else 1.0
        effect_size = math.nan
    else:
        t_statistic = mean_difference / (sd_difference / math.sqrt(n))
        p_value = two_tailed_t_p_value(t_statistic, n - 1)
        effect_size = mean_difference / sd_difference

    return {
        "test_used": "paired t-test",
        "n_pairs": n,
        "t_statistic": t_statistic,
        "degrees_of_freedom": n - 1,
        "p_value": p_value,
        "effect_size_d": effect_size,
    }


def welch_t_test(baseline_values, kg_values):
    baseline = pd.Series(baseline_values).dropna().astype(float)
    kg = pd.Series(kg_values).dropna().astype(float)
    if len(baseline) < 2 or len(kg) < 2:
        return {
            "test_used": "Welch independent t-test",
            "n_pairs": 0,
            "t_statistic": math.nan,
            "degrees_of_freedom": math.nan,
            "p_value": math.nan,
            "effect_size_d": math.nan,
        }

    baseline_var = baseline.var(ddof=1)
    kg_var = kg.var(ddof=1)
    se_squared = baseline_var / len(baseline) + kg_var / len(kg)
    if se_squared == 0 or pd.isna(se_squared):
        t_statistic = 0.0
        degrees_of_freedom = math.nan
        p_value = math.nan
    else:
        t_statistic = (kg.mean() - baseline.mean()) / math.sqrt(se_squared)
        numerator = se_squared**2
        denominator = (baseline_var / len(baseline)) ** 2 / (len(baseline) - 1)
        denominator += (kg_var / len(kg)) ** 2 / (len(kg) - 1)
        degrees_of_freedom = numerator / denominator if denominator else math.nan
        p_value = two_tailed_t_p_value(t_statistic, degrees_of_freedom)

    pooled_numerator = (len(baseline) - 1) * baseline_var + (len(kg) - 1) * kg_var
    pooled_denominator = len(baseline) + len(kg) - 2
    pooled_sd = math.sqrt(pooled_numerator / pooled_denominator) if pooled_denominator else math.nan
    effect_size = (kg.mean() - baseline.mean()) / pooled_sd if pooled_sd else math.nan

    return {
        "test_used": "Welch independent t-test",
        "n_pairs": 0,
        "t_statistic": t_statistic,
        "degrees_of_freedom": degrees_of_freedom,
        "p_value": p_value,
        "effect_size_d": effect_size,
    }


def summarize_scale_scores(questionnaire):
    score_columns = [
        "session_id",
        "participant_id",
        "assistant_version",
        "satisfaction_overall",
        "guided_exploration_overall",
        "trust_benevolence",
        "trust_competence",
        "trust_integrity",
        "trust_overall",
    ]
    if questionnaire.empty:
        return pd.DataFrame(columns=score_columns)

    post = questionnaire[questionnaire["phase"] == "post"].copy()
    post["assistant_version"] = post["assistant_version"].map(normalize_version)

    score_rows = []
    grouping_columns = ["session_id", "participant_id", "assistant_version"]
    for group_key, group in post.groupby(grouping_columns, dropna=False):
        session_id, participant_id, assistant_version = group_key
        item_scores = {
            row.question_id: row.response_numeric
            for row in group.itertuples()
            if pd.notna(row.response_numeric)
        }

        satisfaction_values = [item_scores.get(item_id) for item_id in SATISFACTION_ITEMS]
        guided_exploration_values = [
            item_scores.get(item_id) for item_id in GUIDED_EXPLORATION_ITEMS
        ]

        row = {
            "session_id": session_id,
            "participant_id": participant_id,
            "assistant_version": assistant_version,
            "satisfaction_overall": _mean(satisfaction_values),
            "guided_exploration_overall": _mean(guided_exploration_values),
        }

        for construct in sorted(set(TRUST_ITEMS.values())):
            construct_items = [
                item_scores.get(item_id)
                for item_id, item_construct in TRUST_ITEMS.items()
                if item_construct == construct
            ]
            row[construct] = _mean(construct_items)

        row["trust_overall"] = _mean(
            [
                row["trust_benevolence"],
                row["trust_integrity"],
                row["trust_competence"],
            ]
        )

        score_rows.append(row)

    return pd.DataFrame(score_rows, columns=score_columns)


def summarize_background(questionnaire):
    if questionnaire.empty:
        return pd.DataFrame()

    pre = questionnaire[questionnaire["phase"] == "pre"].copy()
    if pre.empty:
        return pd.DataFrame()

    pre["answer"] = pre["response_text"].fillna(pre["response_numeric"])
    background = pre.pivot_table(
        index="participant_id",
        columns="question_id",
        values="answer",
        aggfunc="first",
    ).reset_index()
    background = background.rename(columns=PRE_ITEMS)
    return background


def summarize_comments(questionnaire):
    if questionnaire.empty:
        return pd.DataFrame()

    comments = questionnaire[
        (questionnaire["phase"] == "post") & questionnaire["response_text"].notna()
    ].copy()
    if comments.empty:
        return pd.DataFrame()

    comments["assistant_version"] = comments["assistant_version"].map(normalize_version)
    comments["question_label"] = comments["question_id"].map(COMMENT_QUESTION_LABELS)
    return comments[
        [
            "participant_id",
            "assistant_version",
            "session_id",
            "question_id",
            "question_label",
            "response_text",
            "submitted_at",
        ]
    ].sort_values(["participant_id", "assistant_version", "question_id"])


def summarize_interactions(interactions):
    if interactions.empty:
        return pd.DataFrame()

    interactions = interactions.copy()
    interactions["assistant_version"] = interactions["assistant_version"].map(normalize_version)
    return interactions[
        [
            "participant_id",
            "assistant_version",
            "session_id",
            "id",
            "user_query",
            "assistant_response",
            "explanation_clicked",
            "user_query_sent_time",
            "response_displayed_time",
        ]
    ].sort_values(["participant_id", "assistant_version", "id"])


def add_interaction_counts(scores, interactions):
    if scores.empty:
        return scores

    if interactions.empty:
        scores["questions_asked"] = 0
        scores["explanations_clicked"] = 0
        return scores

    interactions = interactions.copy()
    interactions["assistant_version"] = interactions["assistant_version"].map(normalize_version)
    counts = (
        interactions.groupby(["session_id", "participant_id", "assistant_version"])
        .agg(
            questions_asked=("user_query", "count"),
            explanations_clicked=("explanation_clicked", "sum"),
        )
        .reset_index()
    )
    return scores.merge(
        counts,
        on=["session_id", "participant_id", "assistant_version"],
        how="left",
    ).fillna({"questions_asked": 0, "explanations_clicked": 0})


def build_version_comparison(scores):
    comparison_columns = [
        "metric",
        "n_baseline",
        "mean_baseline",
        "sd_baseline",
        "median_baseline",
        "min_baseline",
        "max_baseline",
        "n_kg_enhanced",
        "mean_kg_enhanced",
        "sd_kg_enhanced",
        "median_kg_enhanced",
        "min_kg_enhanced",
        "max_kg_enhanced",
        "mean_difference_kg_minus_baseline",
        "median_difference_kg_minus_baseline",
        "test_used",
        "n_pairs",
        "t_statistic",
        "degrees_of_freedom",
        "p_value",
        "effect_size_d",
        "interpretation",
    ]
    metrics = [
        "trust_overall",
        "trust_benevolence",
        "trust_integrity",
        "trust_competence",
        "satisfaction_overall",
        "guided_exploration_overall",
    ]
    rows = []
    if scores.empty:
        empty_rows = []
        for metric in metrics:
            row = {column: math.nan for column in comparison_columns}
            row["metric"] = metric
            row["interpretation"] = "No completed responses yet"
            empty_rows.append(row)
        return pd.DataFrame(empty_rows, columns=comparison_columns)

    for metric in metrics:
        if metric not in scores.columns:
            continue

        baseline = scores[scores["assistant_version"] == "baseline"][
            ["participant_id", metric]
        ].dropna()
        kg = scores[scores["assistant_version"] == "kg_enhanced"][
            ["participant_id", metric]
        ].dropna()
        baseline_values = baseline[metric]
        kg_values = kg[metric]

        paired = baseline.merge(kg, on="participant_id", suffixes=("_baseline", "_kg"))
        if len(paired) >= 2:
            test_result = paired_t_test(
                paired[f"{metric}_baseline"],
                paired[f"{metric}_kg"],
            )
        else:
            test_result = welch_t_test(baseline_values, kg_values)

        p_value = test_result["p_value"]
        if pd.isna(p_value):
            interpretation = "Not enough completed responses yet"
        elif p_value < 0.05:
            interpretation = "p < .05"
        else:
            interpretation = "p >= .05"

        rows.append(
            {
                "metric": metric,
                "n_baseline": len(baseline_values),
                "mean_baseline": baseline_values.mean() if len(baseline_values) else math.nan,
                "sd_baseline": baseline_values.std(ddof=1) if len(baseline_values) > 1 else math.nan,
                "median_baseline": baseline_values.median() if len(baseline_values) else math.nan,
                "min_baseline": baseline_values.min() if len(baseline_values) else math.nan,
                "max_baseline": baseline_values.max() if len(baseline_values) else math.nan,
                "n_kg_enhanced": len(kg_values),
                "mean_kg_enhanced": kg_values.mean() if len(kg_values) else math.nan,
                "sd_kg_enhanced": kg_values.std(ddof=1) if len(kg_values) > 1 else math.nan,
                "median_kg_enhanced": kg_values.median() if len(kg_values) else math.nan,
                "min_kg_enhanced": kg_values.min() if len(kg_values) else math.nan,
                "max_kg_enhanced": kg_values.max() if len(kg_values) else math.nan,
                "mean_difference_kg_minus_baseline": (
                    kg_values.mean() - baseline_values.mean()
                    if len(baseline_values) and len(kg_values)
                    else math.nan
                ),
                "median_difference_kg_minus_baseline": (
                    kg_values.median() - baseline_values.median()
                    if len(baseline_values) and len(kg_values)
                    else math.nan
                ),
                "test_used": test_result["test_used"],
                "n_pairs": test_result["n_pairs"],
                "t_statistic": test_result["t_statistic"],
                "degrees_of_freedom": test_result["degrees_of_freedom"],
                "p_value": p_value,
                "effect_size_d": test_result["effect_size_d"],
                "interpretation": interpretation,
            }
        )

    return pd.DataFrame(rows, columns=comparison_columns)


def build_readme():
    rows = [
        ("Purpose", "This workbook exports study data from interactions.db for thesis analysis."),
        ("Trust scoring", "Benevolence, integrity, and competence are averaged first. Overall trust is the average of those three dimension scores."),
        ("Satisfaction scoring", "The four satisfaction items are averaged into one satisfaction score from 1 to 7."),
        ("Guided exploration scoring", "The guided exploration items are averaged into one score from 1 to 7."),
        ("Participant_Scores", "One row per participant and assistant version with trust dimensions, overall trust, satisfaction, and guided exploration."),
        ("Version_Comparison", "Compares baseline and KG-enhanced versions using medians, ranges, observed differences, and p-values."),
        ("Scale_Items", "Raw numeric questionnaire items for trust, satisfaction, and background controls."),
        ("Comments", "Mandatory open-text comments from the post-questionnaire."),
        ("Comment_Coding_Template", "Suggested qualitative themes for manually coding participant comments."),
        ("Interactions", "Questions asked, assistant answers, and explanation-click metadata."),
        ("P-value", "A p-value below .05 is commonly interpreted as statistical evidence of a difference, but small sample sizes should be discussed cautiously."),
        ("Effect size d", "Positive values mean the KG-enhanced version scored higher than the baseline version."),
    ]
    return pd.DataFrame(rows, columns=["Topic", "Explanation"])


def build_comment_coding_template():
    rows = [
        ("Transparency", "The explanation made the answer process clear or unclear."),
        ("Traceability", "The participant could or could not follow how data, tables, or relationships led to the answer."),
        ("Competence", "The assistant seemed capable, knowledgeable, or technically correct."),
        ("Reliability", "The answer seemed correct, stable, or questionable."),
        ("Uncertainty", "The participant felt unsure whether to rely on the answer."),
        ("Helpfulness", "The assistant or explanation supported the task well."),
        ("Complexity", "The explanation was too difficult, too long, or cognitively demanding."),
        ("Animation", "The animated reasoning path helped or did not help understanding."),
        ("Written explanation", "The written explanation helped or did not help understanding."),
        ("Exploration freedom", "The participant felt free or limited when asking their own question."),
        ("Dataset understanding", "The dataset viewer or examples helped the participant understand what could be asked."),
        ("Enjoyment", "The participant enjoyed or did not enjoy exploring the dataset."),
        ("Satisfaction", "The participant liked or disliked the overall interaction."),
    ]
    return pd.DataFrame(rows, columns=["Suggested theme", "Meaning"])


def autosize_workbook(writer):
    for worksheet in writer.book.worksheets:
        worksheet.freeze_panes = "A2"
        for column_cells in worksheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter
            for cell in column_cells:
                value = "" if cell.value is None else str(cell.value)
                max_length = max(max_length, min(len(value), 70))
            worksheet.column_dimensions[column_letter].width = max(12, max_length + 2)


def _as_database_url(database_source):
    database_source = str(database_source)
    if "://" in database_source:
        return database_source
    return f"sqlite:///{Path(database_source).as_posix()}"


def export_analysis(database_source, output_path):
    database_url = _as_database_url(database_source)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sessions = read_study_table("study_sessions", database_url)
    questionnaire = read_study_table("questionnaire_responses", database_url)
    interactions = read_study_table("interactions", database_url)

    if not sessions.empty:
        sessions["assistant_version"] = sessions["assistant_version"].map(normalize_version)
    if not questionnaire.empty:
        questionnaire["assistant_version"] = questionnaire["assistant_version"].map(normalize_version)

    scores = summarize_scale_scores(questionnaire)
    scores = add_interaction_counts(scores, interactions)
    background = summarize_background(questionnaire)
    if not scores.empty and not background.empty:
        scores = scores.merge(background, on="participant_id", how="left")

    comparison = build_version_comparison(scores)
    comments = summarize_comments(questionnaire)
    interaction_summary = summarize_interactions(interactions)

    scale_items = questionnaire.copy()
    if not scale_items.empty:
        scale_items = scale_items.sort_values(
            ["participant_id", "assistant_version", "phase", "question_id"]
        )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        build_readme().to_excel(writer, sheet_name="Readme", index=False)
        scores.to_excel(writer, sheet_name="Participant_Scores", index=False)
        comparison.to_excel(writer, sheet_name="Version_Comparison", index=False)
        scale_items.to_excel(writer, sheet_name="Scale_Items", index=False)
        comments.to_excel(writer, sheet_name="Comments", index=False)
        build_comment_coding_template().to_excel(
            writer,
            sheet_name="Comment_Coding_Template",
            index=False,
        )
        interaction_summary.to_excel(writer, sheet_name="Interactions", index=False)
        sessions.to_excel(writer, sheet_name="Study_Sessions", index=False)
        autosize_workbook(writer)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Export thesis study analysis workbook.")
    parser.add_argument(
        "--db",
        default="interactions.db",
        help="Path to local interactions.db, used when --database-url is not set",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Hosted study database URL, for example from Supabase/Postgres",
    )
    parser.add_argument(
        "--output",
        default="analysis_outputs/study_analysis.xlsx",
        help="Path for the Excel analysis workbook",
    )
    args = parser.parse_args()

    output_path = export_analysis(args.database_url or args.db, args.output)
    print(f"Analysis workbook created: {output_path}")


if __name__ == "__main__":
    main()
