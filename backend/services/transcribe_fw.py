from pathlib import Path
from faster_whisper import WhisperModel

def transcribe_audio(audio_path: Path, language: str | None, model_size: str = "small" ) -> dict :
    model = WhisperModel(model_size, device="cuda", compute_type="int8")

    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True
    )
    
    out_segments = []
    for s in segments:
        text = (s.text or "").strip()
        if text:
            out_segments.append({
                "start": float(s.start),
                "end": float(s.end),
                "text": text,
            })

    return {
        "language": info.language,
        "duration": float(info.duration),
        "segments": out_segments,
    }    

    