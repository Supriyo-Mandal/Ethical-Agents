import os

import streamlit as st
import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Semantic Risk Analyzer", layout="wide")
st.title("Semantic Risk Analyzer")
st.caption("Upload documents and review the resulting publish decision and audit-style rationale.")

backend_url = st.text_input("FastAPI backend URL", value=BACKEND_URL)

uploaded_file = st.file_uploader("Upload a document", type=["txt", "md", "pdf", "docx"])
if uploaded_file is not None and st.button("Analyze"):
    with st.spinner("Analyzing document..."):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")}
        response = requests.post(f"{backend_url}/upload", files=files, timeout=120)
        if response.ok:
            payload = response.json()
            st.success("Analysis complete")
            st.subheader("Decision")
            st.write(payload["decision"])
            st.write(f"Publish: {'Yes' if payload['publish'] else 'No'}")
            st.write(f"Overall score: {payload['overall_score']}")
            st.subheader("Metadata")
            st.write(payload["paragraph"])
            st.write(payload["summary"])
            st.write("Fields used: " + ", ".join(payload["fields_used"]) if payload["fields_used"] else "None")
            st.write("Description: " + payload["description"])
        else:
            st.error(response.text)

st.subheader("Previous uploads")
try:
    output = requests.get(f"{backend_url}/output", timeout=30)
    if output.ok:
        payload = output.json()
        for item in payload.get("documents", []):
            st.markdown(f"**{item['name']}**")
            st.write(item.get("description", ""))
            st.write(f"Decision: {item.get('decision', 'Unknown')}")
            st.write("---")
except Exception as exc:
    st.info(f"Unable to reach backend: {exc}")
