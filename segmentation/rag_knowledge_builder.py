import logging

import pandas as pd
import yaml

from segmentation.config import TAXONOMY_PATH, VALIDATED_EXAMPLES_PATH, RAG_KNOWLEDGE_PATH

logger = logging.getLogger(__name__)


def load_taxonomy_as_knowledge(taxonomy_path):
    with open(taxonomy_path, "r", encoding="utf-8") as file:
        taxonomy = yaml.safe_load(file)

    rows = []
    sectors = taxonomy.get("sectors", {})

    for sector_name, sector_data in sectors.items():
        definition = sector_data.get("definition", "")
        rules = sector_data.get("rules", [])
        examples = sector_data.get("include_examples", [])

        if definition:
            rows.append({"text": f"{sector_name} definition: {definition}", "category": sector_name, "source": "taxonomy_definition"})
        for rule in rules:
            rows.append({"text": f"{sector_name} business rule: {rule}", "category": sector_name, "source": "taxonomy_rule"})
        for example in examples:
            rows.append({"text": f"Example activity classified as {sector_name}: {example}", "category": sector_name, "source": "taxonomy_example"})

    return pd.DataFrame(rows)


def load_validated_examples_as_knowledge(validated_examples_path):
    try:
        df = pd.read_csv(validated_examples_path, encoding="utf-8-sig")
    except FileNotFoundError:
        return pd.DataFrame(columns=["text", "category", "source"])

    if df.empty:
        return pd.DataFrame(columns=["text", "category", "source"])

    rows = []
    for _, row in df.iterrows():
        activity = str(row.get("activity", "")).strip()
        category = str(row.get("category", "")).strip()
        if activity and category:
            rows.append({
                "text": f"Validated example: '{activity}' should be classified as {category}.",
                "category": category,
                "source": "validated_example",
            })

    return pd.DataFrame(rows)


def add_manual_business_rules():
    rules = [
        {"text": "If an activity is about commerce, vente, selling, trading, distribution, import/export, wholesale or retail of products, classify it as retail.", "category": "retail", "source": "manual_business_rule"},
        {"text": "Selling medical equipment, medical products, construction materials, food, clothes or electronics is retail because the company sells products.", "category": "retail", "source": "manual_business_rule"},
        {"text": "Commerce de matériel médical and vente de dispositifs médicaux are retail, not healthcare, because the activity is selling products.", "category": "retail", "source": "manual_business_rule"},
        {"text": "Cafés, restaurants, salons de beauté, coiffure and beauty salons are retail in this project unless clearly part of a hotel.", "category": "retail", "source": "manual_business_rule"},
        {"text": "Healthcare is only for medical care or health services such as clinics, hospitals, doctors, medical laboratories, dental care, ambulance and medical analysis.", "category": "healthcare", "source": "manual_business_rule"},
        {"text": "Manufacturing means producing, fabricating, transforming, assembling or processing physical goods.", "category": "manufacturing", "source": "manual_business_rule"},
        {"text": "Transport means moving people or goods, logistics, freight, delivery, warehousing, taxi, shipping or transport support.", "category": "transport", "source": "manual_business_rule"},
        {"text": "Tourism means hotels, accommodation, tourist residences, travel agencies, camping and tourism services.", "category": "tourism", "source": "manual_business_rule"},
        {"text": "Education means schools, universities, training centers, teaching, kindergartens, tutoring and learning services.", "category": "education", "source": "manual_business_rule"},
        {"text": "Financial services means banks, insurance, credit, leasing, accounting, audit, investment and financial consulting.", "category": "financial_services", "source": "manual_business_rule"},
        {"text": "Others is the last resort category. Use others only when the activity does not clearly fit retail, manufacturing, transport, tourism, healthcare, education or financial services.", "category": "others", "source": "manual_business_rule"},
    ]
    return pd.DataFrame(rules)


def build_rag_knowledge_base():
    taxonomy_df     = load_taxonomy_as_knowledge(TAXONOMY_PATH)
    validated_df    = load_validated_examples_as_knowledge(VALIDATED_EXAMPLES_PATH)
    manual_rules_df = add_manual_business_rules()

    rag_df = pd.concat([manual_rules_df, taxonomy_df, validated_df], ignore_index=True)
    rag_df = rag_df.dropna(subset=["text", "category"])
    rag_df = rag_df.drop_duplicates(subset=["text", "category", "source"])

    RAG_KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    rag_df.to_csv(RAG_KNOWLEDGE_PATH, index=False, encoding="utf-8-sig")

    logger.info("RAG knowledge base created: %s (%d rows)", RAG_KNOWLEDGE_PATH, len(rag_df))
    logger.info("Sources:\n%s", rag_df["source"].value_counts().to_string())
    logger.info("Categories:\n%s", rag_df["category"].value_counts().to_string())

    return rag_df


if __name__ == "__main__":
    build_rag_knowledge_base()