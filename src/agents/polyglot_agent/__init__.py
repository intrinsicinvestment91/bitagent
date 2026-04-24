import os
import tempfile
import logging

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from src.agents.polyglot_agent.polyglot_agent import PolyglotAgent
from src.security.secure_endpoints import TranslationRequest, sanitize_input
from src.wallets.fedimint_wallet import FedimintWallet

logger = logging.getLogger(__name__)

agent = PolyglotAgent()
router = APIRouter()
_fedimint = FedimintWallet()

_wallet = None


def _get_wallet():
    global _wallet
    if _wallet is None:
        try:
            from agent_wallet import AgentWallet
            _wallet = AgentWallet()
        except Exception:
            pass
    return _wallet


def _payment_invoice(price: int, memo: str):
    wallet = _get_wallet()
    if not wallet:
        return None
    try:
        data = wallet.create_invoice(price, memo)
        inv = {
            "payment_required": True,
            "amount_sats": price,
            "payment_request": data.get("bolt11") or data.get("payment_request"),
            "payment_hash": data.get("payment_hash"),
        }
        if _fedimint.enabled:
            inv["ecash_accepted"] = True
            inv["ecash_amount_msats"] = price * 1000
        return inv
    except Exception as e:
        logger.warning(f"Invoice creation failed: {e}")
        return None


def _verify_payment(payment_hash: str) -> bool:
    wallet = _get_wallet()
    if not wallet:
        return True
    try:
        return wallet.check_invoice(payment_hash)
    except Exception:
        return False


@router.get("/info")
async def get_agent_info():
    return agent.get_info()


@router.get("/services")
async def get_services():
    return {"services": agent.list_services(), "pricing": agent.get_price()}


@router.post("/translate")
async def translate(body: TranslationRequest):
    text = sanitize_input(body.text)
    source = sanitize_input(body.source_lang)
    target = sanitize_input(body.target_lang)
    price = agent.get_price("translate")

    if body.ecash_notes:
        if not await _fedimint.verify_and_receive(body.ecash_notes, price):
            raise HTTPException(402, "Ecash payment invalid or insufficient")
    elif body.payment_hash:
        if not _verify_payment(body.payment_hash):
            raise HTTPException(402, "Payment not verified")
    else:
        invoice = _payment_invoice(price, f"Translate: {text[:40]}")
        if invoice:
            return JSONResponse(status_code=402, content=invoice)

    result = await agent.handle_translation(text, source, target)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), payment_hash: str = None, ecash_notes: str = None):
    price = agent.get_price("transcribe")

    if ecash_notes:
        if not await _fedimint.verify_and_receive(ecash_notes, price):
            raise HTTPException(402, "Ecash payment invalid or insufficient")
    elif payment_hash:
        if not _verify_payment(payment_hash):
            raise HTTPException(402, "Payment not verified")
    else:
        invoice = _payment_invoice(price, "Audio transcription")
        if invoice:
            return JSONResponse(status_code=402, content=invoice)

    audio_bytes = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        result = await agent.handle_transcription(audio_file_path=tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    if "error" in result:
        raise HTTPException(500, result["error"])
    return result


@router.post("/a2a")
async def a2a(body: dict):
    method = body.get("method")
    params = body.get("params", {})

    if method == "polyglot.translate":
        text = params.get("text")
        if not text:
            return {"error": "Missing 'text'"}
        return await agent.handle_translation(
            sanitize_input(text),
            params.get("source_lang", "auto"),
            params.get("target_lang", "en"),
        )

    if method == "polyglot.transcribe":
        audio_data = params.get("audio_data")
        if not audio_data:
            return {"error": "Missing 'audio_data'"}
        return await agent.handle_transcription(audio_data=audio_data)

    return {"error": f"Unsupported method '{method}'"}
