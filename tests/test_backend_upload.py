import asyncio
import io

from fastapi import UploadFile

from backend.app import analysis as analysis_module
from backend.app import storage
from backend.app.api.routes import upload


def test_upload_route_extracts_text_and_returns_previous_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "REPORT_DIRECTORY", tmp_path)
    storage.REPORT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        analysis_module,
        "framework_analyze",
        lambda document: {
            "publish": False,
            "summary": "ok",
            "metadata": {"fields": [{"agent": "Bias", "field": "Risk", "score": 0.9, "reason": "sample"}]},
        },
    )

    upload_file = UploadFile(filename="sample.txt", file=io.BytesIO(b"Alpha beta"))
    response = asyncio.run(upload(upload_file))

    assert response["publish"] is False
    assert response["summary"] == "ok"
    assert response["previous_documents"][0]["name"] == "sample.txt"
    assert response["previous_documents"][0]["publish"] is False
