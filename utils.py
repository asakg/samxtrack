import pandas as pd
import os

def load_latest_loans():
    path = os.path.join("data", "latest_loans.xlsx")
    if not os.path.exists(path):
        return pd.DataFrame()

    df = pd.read_excel(path)


    # Activity from group
    def classify_activity(group):
        return "Active" if str(group).strip().lower() == "active" else "Inactive"

    df["Activity Status"] = df["Group"].apply(classify_activity)
    df["Has Contract"] = df["Contract"].apply(lambda x: str(x).strip().lower() == "yes" if pd.notna(x) else False)
    df["Has Guarantor"] = df["Guarantor"].apply(lambda x: str(x).strip().lower() not in ["", "na", "nan"])
    df["Has Title"] = df["Title Ownership"].apply(lambda x: str(x).strip().lower() in ["sam", "own"])

    # Apply risk after title/guarantor
    def classify_risk(row):
        days = int(row.get("Days Late", 0))
        has_title = row.get("Has Title")
        has_guarantor = row.get("Has Guarantor")
        if days > 21 and not has_title and not has_guarantor:
            return "Critical"
        elif days > 21:
            return "High Risk"
        elif days > 14:
            return "At Risk"
        elif days > 7:
            return "Low Risk"
        else:
            return "Healthy"

    df["Risk Level"] = df.apply(classify_risk, axis=1)

    return df

# Reusable method for table
def dataframe_to_html_table(df, title="Loan Details"):
    if df.empty:
        return f"""
        <div style='margin-top:20px'>
            <h3 style='font-weight:bold;'>{title}</h3>
            <a href='/loan-summary' style='display:inline-block;margin-bottom:10px;'>&larr; Back to Summary</a>
            <div style='background:white;padding:15px;border-radius:5px;'>
                <em>No data available.</em>
            </div>
        </div>
        """

    html = f"""
    <div style='margin-top:20px'>
        <h3 style='font-weight:bold;'>{title}</h3>
        <a href='/loan-summary' style='display:inline-block;margin-bottom:10px;'>&larr; Back to Summary</a>
        <div style='overflow-x:auto;'>
            <table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;background:white;'>
                <thead style='background:#f2f2f2;'>
                    <tr>
                        {''.join(f'<th>{col}</th>' for col in df.columns)}
                    </tr>
                </thead>
                <tbody>
                    {''.join('<tr>' + ''.join(f'<td>{val}</td>' for val in row) + '</tr>' for row in df.values)}
                </tbody>
            </table>
        </div>
    </div>
    """
    return html