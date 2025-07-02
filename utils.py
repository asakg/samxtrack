import pandas as pd
import os

def load_latest_loans():
    path = os.path.join("data", "latest_loans.xlsx")
    if not os.path.exists(path):
        return pd.DataFrame()

    df = pd.read_excel(path)

    # Risk level from status
    def classify_risk(status):
        status = str(status).lower()
        if "3w" in status:
            return "Critical"
        elif "2w" in status:
            return "High Risk"
        elif "1w" in status:
            return "At Risk"
        elif "finished" in status or "paid" in status:
            return "Paid"
        else:
            return "Unknown"

    # Activity from group
    def classify_activity(group):
        return "Active" if str(group).strip().lower() == "active" else "Inactive"

    df["Risk Level"] = df["Status"].apply(classify_risk)
    df["Activity Status"] = df["Group"].apply(classify_activity)
    df["Has Contract"] = df["Contract"].apply(lambda x: str(x).strip().lower() == "yes" if pd.notna(x) else False)
    df["Has Title"] = df["Title Ownership"].apply(lambda x: str(x).strip().lower() in ["sam", "own"])
    df["Has Guarantor"] = df["Guarantor"].notna()

    return df