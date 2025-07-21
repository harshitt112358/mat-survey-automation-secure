import streamlit as st
import pandas as pd
import json
import copy
import io
from datetime import datetime

# ──────────────────────────────
# 🔐 PASSWORD PROTECTION
# ──────────────────────────────
def require_login():

    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # If not authenticated, show password screen
    if not st.session_state.authenticated:
        st.markdown("### 🔐 Secured Access")
        password = st.text_input("Enter app password", type="password")

        if password == st.secrets["app_password"]:
            st.session_state.authenticated = True
            st.success("✅ Access granted. Reloading...")
            st.rerun()  # <- updated here
        elif password:
            st.error("❌ Incorrect password")

        st.stop()  # Prevent rest of app from showing

require_login()

# ──────────────────────────────
# 🎨 PAGE CONFIG + HEADER
# ──────────────────────────────
st.set_page_config(page_title="MAT Survey Automation Tool", layout="centered")

col1, col2 = st.columns([1, 4], gap="small")
with col1:
    st.image("bain_logo.png", width=140)
with col2:
    st.markdown("## 📝 MAT Survey Automation Tool")

st.markdown(
    """
**Instructions**

1) Upload the **Excel** and **Base QSF** file.  
2) Click **“Generate Updated QSF”** to apply edits and download the result.
"""
)

# ──────────────────────────────
# 📤 FILE UPLOADS
# ──────────────────────────────
excel_file = st.file_uploader("📄 Excel mapping file (.xlsx)", type=["xlsx"])
qsf_file   = st.file_uploader("📁 Base QSF file (.qsf)", type=["qsf", "json"])
process_btn = st.button("🚀 Generate Updated QSF", disabled=not (excel_file and qsf_file))

# ──────────────────────────────
# 🧠 QSF EDIT LOGIC
# ──────────────────────────────
def apply_edits(df: pd.DataFrame, qsf_data: dict) -> tuple[dict, set[str]]:
    qsf = copy.deepcopy(qsf_data)
    grouped = df.groupby("QuestionID")
    updated_elements = []
    deleted_qids: set[str] = set()

    for el in qsf["SurveyElements"]:
        if el.get("Element") != "SQ":
            updated_elements.append(el)
            continue

        qid     = el["PrimaryAttribute"]
        payload = el["Payload"]

        if qid not in grouped.groups:
            updated_elements.append(el)
            continue

        group = grouped.get_group(qid)

        question_row = group[group["ElementType"] == "QuestionText"]
        if (
            not question_row.empty
            and str(question_row["Display Question (Yes/No)"].iloc[0]).strip().lower() == "no"
        ):
            deleted_qids.add(qid)
            continue

        if "Display Logic (On/Off)" in group.columns:
            logic_flags = (
                group["Display Logic (On/Off)"]
                .dropna().astype(str).str.strip().str.lower()
            )
            if "no" in logic_flags.values:
                payload.pop("DisplayLogic", None)

        for _, row in group.iterrows():
            etype        = row["ElementType"]
            edited_text  = row.get("EditedText", "")
            display_flag = str(row.get("Display Question (Yes/No)", "")).strip().lower()
            label        = str(row.get("Label", "")).strip()
            original     = str(row.get("OriginalText", "")).strip()

            if etype == "QuestionText" and pd.notna(edited_text):
                payload["QuestionText"] = edited_text

            elif etype.startswith("ChoiceText") and "Choices" in payload:
                try:
                    choice_id = etype.split(" - ")[1].strip()
                    if display_flag == "no":
                        payload["Choices"].pop(choice_id, None)
                        continue

                    if choice_id not in payload["Choices"]:
                        continue

                    if pd.isna(edited_text) and pd.isna(original):
                        content = "Don't know"
                    else:
                        content = edited_text if pd.notna(edited_text) else original

                    if choice_id in ("1", "2", "3") and label and content:
                        display_html = f"<strong>{label}</strong>\n{content}"
                    else:
                        display_html = content

                    payload["Choices"][choice_id]["Display"] = display_html
                except Exception:
                    pass

        updated_elements.append(el)

    for el in updated_elements:
        if el.get("Element") == "BL":
            pl = el.get("Payload")
            if isinstance(pl, dict):
                pl["BlockElements"] = [
                    be for be in pl.get("BlockElements", [])
                    if be.get("Type") != "Question"
                       or be.get("QuestionID") not in deleted_qids
                ]

    qsf["SurveyElements"] = updated_elements
    return qsf, deleted_qids

# ──────────────────────────────
# 🚀 PROCESS + DOWNLOAD
# ──────────────────────────────
if process_btn:
    try:
        df = pd.read_excel(excel_file, sheet_name="Sheet1")
        qsf_raw = json.load(qsf_file)
        updated_qsf, deleted_qids = apply_edits(df, qsf_raw)

        json_bytes = json.dumps(updated_qsf, indent=2, allow_nan=False).encode("utf-8")
        memfile    = io.BytesIO(json_bytes)

        outname = f"Updated_Survey_{datetime.now():%Y%m%d_%H%M%S}.qsf"

        st.success("✅ QSF file successfully updated!")
        if deleted_qids:
            st.info("🗑️ Questions Deleted: " + ", ".join(sorted(deleted_qids)))

        st.download_button(
            "⬇️ Download Updated QSF",
            data=memfile,
            file_name=outname,
            mime="application/json",
        )

    except Exception as e:
        st.error(f"❌ Error: {e}")
