from fastapi import APIRouter, File, UploadFile

from app.api.analyze import analyze_document_route
from app.api.report import list_reports_route
from app.api.upload import upload_document_route

router = APIRouter()
router.add_api_route("/upload", upload_document_route, methods=["POST"])
router.add_api_route("/analyze", analyze_document_route, methods=["POST"])
router.add_api_route("/output", list_reports_route, methods=["GET"])
router.add_api_route("/reports", list_reports_route, methods=["GET"])
