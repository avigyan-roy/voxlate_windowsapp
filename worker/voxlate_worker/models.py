"""Local model adapters. Every adapter records its rights so the UI/bench never hides them.

Selection via environment variables (defaults are the commercially-clean path):
  VOXLATE_ASR = large-v3-turbo | small | medium      (faster-whisper, MIT)
  VOXLATE_MT  = indictrans2 | nllb                    (MIT | CC-BY-NC-4.0)
  VOXLATE_TTS = kokoro_openvoice | xtts               (Apache-2.0+MIT | Coqui CPML non-commercial)
  VOXLATE_DEVICE = cuda | cpu
"""
import os
import tempfile
from pathlib import Path

import numpy as np

from . import COMPLETE, DATA_DIR, model_dir

LANG_TAG = {"hi": "hin_Deva", "en": "eng_Latn"}


def _torch():
    import torch

    if os.name == "nt":  # let ctranslate2 find cuBLAS/cuDNN shipped inside the torch wheel
        os.add_dll_directory(str(Path(torch.__file__).parent / "lib"))
    return torch


def pick_device() -> str:
    want = os.environ.get("VOXLATE_DEVICE")
    if want:
        return want
    return "cuda" if _torch().cuda.is_available() else "cpu"


def hf_path(repo: str) -> str:
    """Local folder written by fetch_models. Never touches the network or the HF symlink cache."""
    d = model_dir(repo)
    if not (d / COMPLETE).exists():
        raise RuntimeError(f"Model {repo} is not downloaded (expected in {d}). "
                           "Run 'Voxlate - Repair setup' from the Start menu.")
    return str(d)


def indic_processor():
    try:
        from IndicTransToolkit import IndicProcessor
    except ImportError:
        from IndicTransToolkit.IndicTransToolkit import IndicProcessor
    return IndicProcessor


# ---------------------------------------------------------------- VAD
class SileroVAD:
    """Silero VAD (MIT). Feed 512-sample chunks at 16 kHz."""
    rights = "MIT"

    def __init__(self):
        from silero_vad import VADIterator, load_silero_vad

        self.torch = _torch()
        self.it = VADIterator(load_silero_vad(onnx=False), threshold=0.5, sampling_rate=16000,
                              min_silence_duration_ms=450, speech_pad_ms=60)

    def __call__(self, chunk: np.ndarray):
        r = self.it(self.torch.from_numpy(chunk))
        return None if not r else ("start" if "start" in r else "end")

    def reset(self):
        self.it.reset_states()


# ---------------------------------------------------------------- ASR
class WhisperASR:
    rights = "MIT (OpenAI Whisper weights, SYSTRAN faster-whisper)"
    REPOS = {"large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",  # renamed repo, same folder name
             "small": "Systran/faster-whisper-small",
             "medium": "Systran/faster-whisper-medium"}

    def __init__(self, size: str, device: str):
        _torch()
        from faster_whisper import WhisperModel

        self.name = f"faster-whisper {size}"
        self.m = WhisperModel(hf_path(self.REPOS.get(size, size)), device=device,
                              compute_type="int8_float16" if device == "cuda" else "int8")

    def words(self, audio16k: np.ndarray, lang: str, prompt: str = "") -> list:
        """-> [(word, start_s, end_s)] relative to the buffer start. Language is forced (no auto-detect)."""
        segs, _ = self.m.transcribe(audio16k, language=lang, task="transcribe", beam_size=1, word_timestamps=True,
                                    condition_on_previous_text=False, initial_prompt=prompt or None, vad_filter=False)
        return [(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or []) if any(c.isalnum() for c in w.word)]


# ---------------------------------------------------------------- Translation
class IndicTrans2:
    rights = "MIT (AI4Bharat IndicTrans2 distilled 200M)"
    REPOS = {("hi", "en"): "ai4bharat/indictrans2-indic-en-dist-200M",
             ("en", "hi"): "ai4bharat/indictrans2-en-indic-dist-200M"}

    def __init__(self, device: str):
        torch = _torch()
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.name, self.device, self.torch = "IndicTrans2-dist-200M", device, torch
        self.ip = indic_processor()(inference=True)
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.m = {}
        for pair, repo in self.REPOS.items():
            path = hf_path(repo)
            self.m[pair] = (AutoTokenizer.from_pretrained(path, trust_remote_code=True),
                            AutoModelForSeq2SeqLM.from_pretrained(path, trust_remote_code=True, torch_dtype=dtype).to(device).eval())

    def __call__(self, text: str, src: str, tgt: str) -> str:
        tok, model = self.m[(src, tgt)]
        batch = self.ip.preprocess_batch([text], src_lang=LANG_TAG[src], tgt_lang=LANG_TAG[tgt])
        inp = tok(batch, truncation=True, padding="longest", return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            out = model.generate(**inp, use_cache=True, min_length=0, max_length=256, num_beams=1)
        dec = tok.batch_decode(out, skip_special_tokens=True, clean_up_tokenization_spaces=True)
        return self.ip.postprocess_batch(dec, lang=LANG_TAG[tgt])[0].strip()


class NLLB:
    rights = "CC-BY-NC-4.0 — NON-COMMERCIAL ONLY (comparison path)"
    REPO = "facebook/nllb-200-distilled-600M"

    def __init__(self, device: str):
        torch = _torch()
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.name, self.device, self.torch = "NLLB-200-distilled-600M", device, torch
        path = hf_path(self.REPO)
        self.tok = AutoTokenizer.from_pretrained(path)
        self.m = AutoModelForSeq2SeqLM.from_pretrained(
            path, torch_dtype=torch.float16 if device == "cuda" else torch.float32).to(device).eval()

    def __call__(self, text: str, src: str, tgt: str) -> str:
        self.tok.src_lang = LANG_TAG[src]
        inp = self.tok(text, return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            out = self.m.generate(**inp, forced_bos_token_id=self.tok.convert_tokens_to_ids(LANG_TAG[tgt]),
                                  max_length=256, num_beams=1)
        return self.tok.batch_decode(out, skip_special_tokens=True)[0].strip()


# ---------------------------------------------------------------- Voice
class ToneConverter:
    """OpenVoice V2 tone-color converter (MIT), in-memory version of openvoice.api.ToneColorConverter."""

    def __init__(self, device: str):
        torch = self.torch = _torch()
        from openvoice import utils
        from openvoice.mel_processing import spectrogram_torch
        from openvoice.models import SynthesizerTrn

        ckpt = Path(hf_path("myshell-ai/OpenVoiceV2")) / "converter"
        self.hps = h = utils.get_hparams_from_file(str(ckpt / "config.json"))
        self.spec_fn, self.device, self.sr = spectrogram_torch, device, h.data.sampling_rate
        self.m = SynthesizerTrn(len(getattr(h, "symbols", [])), h.data.filter_length // 2 + 1,
                                n_speakers=h.data.n_speakers, **h.model).to(device).eval()
        # Official MIT checkpoint from a pinned HF snapshot; contains non-tensor metadata, hence weights_only=False.
        self.m.load_state_dict(torch.load(ckpt / "checkpoint.pth", map_location=device, weights_only=False)["model"], strict=False)

    def _spec(self, audio):
        h = self.hps.data
        y = self.torch.from_numpy(np.ascontiguousarray(audio, np.float32)).to(self.device).unsqueeze(0)
        return self.spec_fn(y, h.filter_length, h.sampling_rate, h.hop_length, h.win_length, center=False)

    def se(self, audio: np.ndarray):
        with self.torch.inference_mode():
            return self.m.ref_enc(self._spec(audio).transpose(1, 2)).unsqueeze(-1)

    def convert(self, audio: np.ndarray, src_se, tgt_se, tau=0.3) -> np.ndarray:
        with self.torch.inference_mode():
            spec = self._spec(audio)
            lens = self.torch.LongTensor([spec.size(-1)]).to(self.device)
            return self.m.voice_conversion(spec, lens, sid_src=src_se, sid_tgt=tgt_se, tau=tau)[0][0, 0].float().cpu().numpy()


SE_SAMPLE = {
    "en": "The quick brown fox jumps over the lazy dog. We will meet tomorrow to talk about the plan.",
    "hi": "नमस्ते, आज मौसम बहुत अच्छा है। हम कल फिर से मिलकर योजना पर बात करेंगे।",
}


class KokoroOpenVoice:
    """Kokoro generic TTS (Apache-2.0) in the target language, then OpenVoice V2 converts the
    timbre to the enrolled owner's voice. Hindi through OpenVoice is UNVERIFIED -> bench it."""
    rights = "Kokoro-82M Apache-2.0 + OpenVoice V2 MIT (commercial use permitted by these licenses)"
    # Base voice chosen by closeness of pitch to the owner's median F0 (not a gender label).
    VOICES = {"en": {"low": "am_michael", "high": "af_heart"}, "hi": {"low": "hm_omega", "high": "hf_alpha"}}

    def __init__(self, device: str, ref: tuple | None, median_f0: float | None):
        import soxr
        from kokoro import KModel, KPipeline

        self.soxr, self.name = soxr, "Kokoro-82M + OpenVoice V2"
        # Model, config and voices from the local folder: KPipeline would otherwise hf_hub_download them.
        repo = "hexgrad/Kokoro-82M"
        kdir = Path(hf_path(repo))
        model = KModel(repo_id=repo, config=str(kdir / "config.json"), model=str(kdir / "kokoro-v1_0.pth")).to(device).eval()
        self.pipes = {"en": KPipeline(lang_code="a", repo_id=repo, model=model),
                      "hi": KPipeline(lang_code="h", repo_id=repo, model=model)}
        band = "low" if (median_f0 or 200) < 165 else "high"
        # Pass voice tensors, not names (a name triggers hf_hub_download; a path is split on commas by load_voice).
        import torch
        self.voice = {l: torch.load(kdir / "voices" / f"{v[band]}.pt", weights_only=True) for l, v in self.VOICES.items()}
        self.conv = None
        if ref is not None:
            self.conv = ToneConverter(device)
            a, sr = ref
            self.tgt_se = self.conv.se(soxr.resample(a, sr, self.conv.sr))
            self.src_se = {l: self.conv.se(soxr.resample(self._kokoro(t, l), 24000, self.conv.sr)) for l, t in SE_SAMPLE.items()}

    @property
    def cloned(self) -> bool:
        return self.conv is not None

    def _kokoro(self, text, lang) -> np.ndarray:
        parts = [r.audio.cpu().numpy() for r in self.pipes[lang](text, voice=self.voice[lang], speed=1.0) if r.audio is not None]
        return np.concatenate(parts).astype(np.float32) if parts else np.zeros(0, np.float32)

    def __call__(self, text: str, lang: str) -> tuple:
        a = self._kokoro(text, lang)
        if not self.conv or not len(a):
            return a, 24000
        return self.conv.convert(self.soxr.resample(a, 24000, self.conv.sr), self.src_se[lang], self.tgt_se), self.conv.sr


class XTTS:
    """Coqui XTTS-v2: direct Hindi/English cloning. Comparison path only."""
    rights = "Coqui Public Model License — NON-COMMERCIAL ONLY; outputs also restricted"

    def __init__(self, device: str, ref: tuple):
        import json

        import soundfile as sf
        manifest = DATA_DIR / "models" / "manifest.json"
        if "coqui/XTTS-v2" not in (json.loads(manifest.read_text())["models"] if manifest.exists() else {}):
            raise RuntimeError("XTTS-v2 not installed/accepted. Run: python -m voxlate_worker.fetch_models --xtts")
        os.environ["COQUI_TOS_AGREED"] = "1"  # accepted explicitly at fetch time; prevents a stdin prompt
        from TTS.api import TTS

        self.name = "XTTS-v2"
        self.m = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device).synthesizer.tts_model
        a, sr = ref
        with tempfile.TemporaryDirectory() as d:  # decrypted reference exists on disk only for this call
            p = os.path.join(d, "ref.wav")
            sf.write(p, a, sr)
            self.lat, self.emb = self.m.get_conditioning_latents(audio_path=[p])

    cloned = True

    def __call__(self, text: str, lang: str) -> tuple:
        out = self.m.inference(text, lang, self.lat, self.emb, temperature=0.7, enable_text_splitting=False)
        return np.asarray(out["wav"], np.float32), 24000


# ---------------------------------------------------------------- Bundle
class Models:
    def __init__(self, log=lambda m: None):
        from . import profile

        torch = _torch()
        self.device = pick_device()
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        asr = os.environ.get("VOXLATE_ASR", "large-v3-turbo" if self.device == "cuda" else "small")
        mt = os.environ.get("VOXLATE_MT", "indictrans2")
        tts = os.environ.get("VOXLATE_TTS", "kokoro_openvoice")
        log(f"Loading VAD + ASR ({asr}) on {self.device}")
        self.vad_factory = SileroVAD
        self.asr = WhisperASR(asr, self.device)
        log(f"Loading translation ({mt})")
        self.mt = (NLLB if mt == "nllb" else IndicTrans2)(self.device)
        self.load_voice(log)

    def load_voice(self, log=lambda m: None):
        """(Re)build only the voice. Enrollment save/delete calls this instead of reloading ASR + MT:
        a full second bundle does not fit next to the first in 4 GB VRAM."""
        from . import profile

        torch = _torch()
        tts = os.environ.get("VOXLATE_TTS", "kokoro_openvoice")
        ref = profile.load() if profile.exists() else None
        f0 = profile.meta().get("quality", {}).get("median_f0")
        log(f"Loading voice ({tts}); owner profile {'found' if ref else 'MISSING'}")
        self.tts = None  # free the old voice first
        if self.device == "cuda":
            torch.cuda.empty_cache()
        if tts == "xtts":
            if ref is None:
                raise RuntimeError("XTTS path needs an enrolled voice profile")
            self.tts = XTTS(self.device, ref)
        else:
            self.tts = KokoroOpenVoice(self.device, ref, f0)
        self.info = {
            "device": self.device,
            "gpu": torch.cuda.get_device_name(0) if self.device == "cuda" else None,
            "asr": self.asr.name, "mt": self.mt.name, "tts": self.tts.name,
            "voice": "cloned" if self.tts.cloned else "generic (debug fallback, NOT your voice)",
            "rights": {"asr": WhisperASR.rights, "mt": type(self.mt).rights, "tts": type(self.tts).rights},
            "peak_vram_mb": self.peak_vram_mb(),
        }

    def peak_vram_mb(self):
        torch = _torch()
        return round(torch.cuda.max_memory_allocated() / 2**20) if self.device == "cuda" else None
