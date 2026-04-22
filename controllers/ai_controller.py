"""
AI Controller Module — Resume Builder + ATS Score Checker
==========================================================
Endpoints:
  POST /api/ai/resume      — Structured resume generation
  POST /api/ai/ats-score   — File-upload based ATS analysis
  POST /api/ai/chat        — AI chat (unchanged)
  POST /api/ai/image       — Image generation (unchanged)
"""

import os
import io
import json
import base64
import re
from datetime import datetime, timezone

import requests
from flask import request, jsonify
from dotenv import load_dotenv

from config.db import db
from models.user_model import increment_usage
from controllers.realtime_controller import get_realtime_data

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

activity_collection = db["activities"]
resume_history_collection = db["resume_history"]

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODEL = "gemini-2.5-flash-lite"
HF_IMAGE_API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _log_activity(user_id, activity_type, input_text, output_text):
    try:
        activity_collection.insert_one({
            "user_id": user_id,
            "type": activity_type,
            "input": input_text,
            "output": output_text[:500] if output_text else "",
            "created_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        print(f"[Activity Log Error] {e}")


def _gemini_key_ok():
    return GEMINI_API_KEY and GEMINI_API_KEY not in ("your_google_ai_studio_api_key_here", "your_gemini_api_key_here")


def _call_gemini(system_prompt: str, user_prompt: str, temperature: float = 0.5, max_tokens: int = 2048) -> str:
    """Call Gemini and return the text response, or raise an exception."""
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GEMINI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        try:
            err = resp.json()
            detail = err.get("error", {}).get("message", str(err)) if isinstance(err, dict) else str(err)
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError(f"Gemini API error: {detail}")
    return resp.json()["choices"][0]["message"]["content"]


def _extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract plain text from PDF or DOCX bytes."""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "pdf":
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n".join(text_parts)

    elif ext in ("docx", "doc"):
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    else:
        raise ValueError(f"Unsupported file type: .{ext}. Please upload PDF or DOCX.")


def _parse_ats_json(raw: str) -> dict:
    """Attempt to extract JSON from AI response, fall back to raw text."""
    try:
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        return json.loads(cleaned)
    except Exception:
        return {
            "score": 0,
            "matched_keywords": [],
            "missing_keywords": [],
            "suggestions": raw,
            "raw": True,
        }


# ── Resume Generation ──────────────────────────────────────────────────────────

def generate_resume(current_user: dict):
    """
    POST /api/ai/resume
    Accepts structured resume data and returns AI-generated resume text.

    Body (JSON):
    {
      "personal": { "name": str, "email": str, "phone": str, "location": str, "summary": str },
      "education": [{ "degree": str, "institution": str, "year": str, "gpa": str }],
      "experience": [{ "role": str, "company": str, "duration": str, "description": str }],
      "skills": [str, ...],
      "projects": [{ "name": str, "description": str, "tech": str }]
    }
    """
    if not _gemini_key_ok():
        return jsonify({"success": False, "message": "Gemini API key is not configured."}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Request body is required."}), 400

        personal = data.get("personal", {})
        name = personal.get("name", "").strip()
        if not name:
            return jsonify({"success": False, "message": "Name is required."}), 400

        # Build structured prompt
        education_items = data.get("education", [])
        experience_items = data.get("experience", [])
        skills = data.get("skills", [])
        projects = data.get("projects", [])

        edu_text = "\n".join(
            f"  - {e.get('degree', '')} at {e.get('institution', '')} ({e.get('year', '')}) {('GPA: ' + e['gpa']) if e.get('gpa') else ''}"
            for e in education_items if e.get("degree") or e.get("institution")
        ) or "  Not provided"

        exp_text = "\n".join(
            f"  - {e.get('role', 'Role')} at {e.get('company', 'Company')} ({e.get('duration', '')})\n    {e.get('description', '')}"
            for e in experience_items if e.get("role") or e.get("company")
        ) or "  Not provided"

        skills_text = ", ".join(skills) if skills else "Not provided"

        proj_text = "\n".join(
            f"  - {p.get('name', '')}: {p.get('description', '')} [Tech: {p.get('tech', '')}]"
            for p in projects if p.get("name")
        ) or "  None"

        user_prompt = f"""Create a complete, professional, ATS-optimized resume in clean Markdown format for:

**PERSONAL INFO**
Name: {name}
Email: {personal.get('email', '')}
Phone: {personal.get('phone', '')}
Location: {personal.get('location', '')}
Professional Summary: {personal.get('summary', 'Write a compelling summary based on the profile')}

**EDUCATION**
{edu_text}

**WORK EXPERIENCE**
{exp_text}

**SKILLS**
{skills_text}

**PROJECTS**
{proj_text}

Instructions:
- Use clean Markdown with proper headings (#, ##, ###)
- Include an impressive professional summary
- Use strong action verbs for experience bullet points
- Format skills as a clean categorized list
- Make it ATS-friendly with relevant keywords
- Output ONLY the resume — no preamble or commentary
"""
        resume_md = _call_gemini(
            system_prompt="You are an elite resume writer and career coach specializing in ATS-optimized resumes.",
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=3000,
        )

        user_id = current_user.get("user_id")
        _log_activity(user_id, "resume", f"Generate resume for {name}", resume_md[:500])
        increment_usage(user_id, "resume_count")

        # Save to history
        try:
            resume_history_collection.insert_one({
                "user_id": user_id,
                "name": name,
                "resume_text": resume_md,
                "input_data": data,
                "created_at": datetime.now(timezone.utc),
            })
        except Exception as e:
            print(f"[Resume History Save Error] {e}")

        return jsonify({
            "success": True,
            "message": "Resume generated successfully.",
            "data": {
                "resume": resume_md,
                "name": name,
                "model": GEMINI_MODEL,
            },
        }), 200

    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Request timed out. Please try again."}), 504
    except Exception as exc:
        import traceback
        print(f"[Resume Error] {exc}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": f"Resume generation failed: {str(exc)}"}), 500


# ── ATS Score (File Upload) ────────────────────────────────────────────────────

def generate_score(current_user: dict):
    """
    POST /api/ai/ats-score  (multipart/form-data)
    Fields:
      - resume_file   : PDF or DOCX file
      - job_description (optional): plain text

    Returns structured JSON with score, matched_keywords, missing_keywords, suggestions.
    """
    if not _gemini_key_ok():
        return jsonify({"success": False, "message": "Gemini API key is not configured."}), 503

    try:
        # Support both file upload and raw text (for backward compat)
        resume_text = ""
        filename = "resume.txt"

        if "resume_file" in request.files:
            file = request.files["resume_file"]
            if not file or file.filename == "":
                return jsonify({"success": False, "message": "No file selected."}), 400
            filename = file.filename
            file_bytes = file.read()
            if len(file_bytes) > 5 * 1024 * 1024:  # 5 MB limit
                return jsonify({"success": False, "message": "File too large. Maximum 5 MB."}), 400
            resume_text = _extract_text_from_file(file_bytes, filename)
        else:
            # Fallback: JSON body with file_url or resume_text
            data = request.get_json(silent=True) or {}
            file_url = data.get("file_url")
            if file_url:
                # Resolve local file
                local_filename = file_url.rsplit("/", 1)[-1]
                filepath = os.path.join(os.getcwd(), "uploads", local_filename)
                if not os.path.exists(filepath):
                    return jsonify({"success": False, "message": "Uploaded file not found on server."}), 404
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                filename = local_filename
                resume_text = _extract_text_from_file(file_bytes, filename)
            else:
                resume_text = data.get("resume_text", "").strip()

        if not resume_text or len(resume_text.strip()) < 50:
            return jsonify({"success": False, "message": "Could not extract enough text from file. Ensure the file is not empty or image-only."}), 400

        job_description = request.form.get("job_description", "") or (request.get_json(silent=True) or {}).get("job_description", "")

        user_prompt = f"""You are an expert ATS (Applicant Tracking System) evaluator and HR recruiter.

Analyze this resume and return a JSON object (no markdown, no explanation, pure JSON):

{{
  "score": <0-100 integer>,
  "grade": "<A/B/C/D/F>",
  "matched_keywords": [<list of keywords found>],
  "missing_keywords": [<list of important missing keywords>],
  "strengths": [<2-4 bullet points about resume strengths>],
  "suggestions": [<3-5 specific actionable improvement suggestions>],
  "summary": "<2-sentence overall assessment>"
}}

{"JOB DESCRIPTION (match against this):" + chr(10) + job_description if job_description.strip() else "No job description provided - do general ATS analysis."}

RESUME TEXT:
{resume_text[:4000]}
"""
        raw = _call_gemini(
            system_prompt="You are a precise ATS evaluator. Always respond with valid JSON only. No markdown fences, no extra text.",
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=1500,
        )

        result = _parse_ats_json(raw)

        user_id = current_user.get("user_id")
        _log_activity(user_id, "score", filename, f"Score: {result.get('score', 0)}")
        increment_usage(user_id, "score_count")

        return jsonify({
            "success": True,
            "message": "Resume analyzed successfully.",
            "data": result,
        }), 200

    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Analysis timed out. Please try again."}), 504
    except Exception as exc:
        import traceback
        print(f"[ATS Score Error] {exc}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": f"Analysis failed: {str(exc)}"}), 500


# ── Chat ───────────────────────────────────────────────────────────────────────

def chat(current_user: dict):
    """POST /api/ai/chat — AI chat using Gemini."""
    if not _gemini_key_ok():
        return jsonify({"success": False, "message": "Gemini API key is not configured."}), 503
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Request body is required."}), 400
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"success": False, "message": "Message is required."}), 400

        # Detect attachment in message: e.g. [Attached: /uploads/abc.pdf]
        attachment_text = ""
        attachment_image_b64 = None
        attachment_mime = None
        
        match = re.search(r'\[Attached:\s*(/uploads/[^\]]+)\]', message)
        if match:
            file_url = match.group(1)
            # Remove the marker from the user message log
            message = message.replace(match.group(0), "").strip()
            
            # Resolve local file
            local_filename = file_url.rsplit("/", 1)[-1]
            filepath = os.path.join(os.getcwd(), "uploads", local_filename)
            if os.path.exists(filepath):
                ext = local_filename.rsplit(".", 1)[-1].lower()
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                    
                if ext in ["pdf", "docx", "doc", "txt", "md"]:
                    try:
                        extracted = _extract_text_from_file(file_bytes, local_filename) if ext != "txt" and ext != "md" else file_bytes.decode("utf-8")
                        attachment_text = f"\n\n--- FILE ATTACHMENT ({local_filename}) ---\n{extracted}\n--- END ATTACHMENT ---\n"
                    except Exception as e:
                        attachment_text = f"\n[System: Uploaded document could not be read: {str(e)}]"
                elif ext in ["jpg", "jpeg", "png", "webp"]:
                    attachment_image_b64 = base64.b64encode(file_bytes).decode("utf-8")
                    attachment_mime = f"image/{'jpeg' if ext == 'jpg' else ext}"

        realtime_info, category = get_realtime_data(message)
        system_prompt = "You are a ultra-modern AI assistant. Provide clear, accurate, and helpful responses."
        
        user_content = message + attachment_text

        if realtime_info:
            system_prompt += f"\n\nCONTEXT: You have access to real-time {category} data fetched via API."
            user_content += f"\n\nLive API Data Found: {realtime_info}\n\nPlease explain this live data to the user and answer their question based on it. Mention that this is real-time information."

        headers = {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"}
        
        # Build messages payload
        messages_payload = [{"role": "system", "content": system_prompt}]
        
        if attachment_image_b64:
            # Multi-modal payload via OpenAI spec
            messages_payload.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_content if user_content else "Please analyze this attached image."},
                    {"type": "image_url", "image_url": {"url": f"data:{attachment_mime};base64,{attachment_image_b64}"}}
                ]
            })
        else:
            messages_payload.append({"role": "user", "content": user_content})

        payload = {
            "model": "gemini-2.5-flash", # Upgrade to standard flash for better multi-modal capability
            "messages": messages_payload,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
        
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            resp_json = response.json()
            detail = resp_json.get("error", {}).get("message", str(resp_json)) if isinstance(resp_json, dict) else str(resp_json)
            return jsonify({"success": False, "message": f"Gemini API error: {detail}"}), 502

        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]

        user_id = current_user.get("user_id")
        _log_activity(user_id, "chat", message, ai_reply)
        increment_usage(user_id, "chat_count")

        return jsonify({
            "success": True,
            "message": "Chat response generated successfully.",
            "data": {
                "reply": ai_reply,
                "model": GEMINI_MODEL,
                "source": "Real-time API + AI" if realtime_info else "NeuralForge AI",
                "category": category if category else "General",
                "usage": result.get("usage", {}),
            },
        }), 200

    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Request timed out."}), 504
    except Exception as exc:
        import traceback
        print(f"[Chat Error] {exc}")
        return jsonify({"success": False, "message": f"Internal Error: {str(exc)}\n\n{traceback.format_exc()}"}), 500


# ── Image Generation ───────────────────────────────────────────────────────────

def generate_image(current_user: dict):
    """POST /api/ai/image — Image generation using HuggingFace."""
    if not HUGGINGFACE_API_KEY or HUGGINGFACE_API_KEY == "your_huggingface_api_key_here":
        return jsonify({"success": False, "message": "HuggingFace API key is not configured."}), 503
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "Request body is required."}), 400
        prompt = data.get("prompt", "").strip()
        if not prompt:
            return jsonify({"success": False, "message": "Prompt is required."}), 400

        headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}", "Content-Type": "application/json"}
        payload = {"inputs": prompt, "parameters": {"num_inference_steps": 30, "guidance_scale": 7.5}}

        response = requests.post(HF_IMAGE_API_URL, headers=headers, json=payload, timeout=120)
        if response.status_code != 200:
            try:
                error_detail = response.json().get("error", "Unknown error")
            except Exception:
                error_detail = response.text[:200]
            return jsonify({"success": False, "message": f"HuggingFace API error: {error_detail}"}), 502

        image_base64 = base64.b64encode(response.content).decode("utf-8")
        user_id = current_user.get("user_id")
        _log_activity(user_id, "image", prompt, f"[Image generated: {len(response.content)} bytes]")
        increment_usage(user_id, "image_count")

        return jsonify({
            "success": True,
            "message": "Image generated successfully.",
            "data": {"image_base64": image_base64, "content_type": "image/png", "prompt": prompt},
        }), 200

    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Image generation timed out."}), 504
    except Exception as exc:
        print(f"[Image Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500
