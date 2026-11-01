# Voxlate · Desktop pipeline, commercial models, server specs, costs, subscription

Prepared 29 Oct 2026. Prices come from public sources (listed at the end) and change often. **Every cost, capacity and price below is a planning estimate.** Load-test and confirm provider prices before budgeting. Licences marked **verify** must be checked on the model card before shipping.

---

## 1. Product shape: one desktop app, two engines

```
                   ┌─────────────────────── Voxlate.exe (Qt desktop app, Windows) ───────────────────────┐
                   │  Mic select · ON switch · languages · mode · meters · voice setup · tray            │
                   │                                                                                     │
  Physical mic ──► │  Capture (WASAPI) ─► Silero VAD ─►  ┌───────────── Engine (choose one) ─────────────┐ │
                   │                                     │ LOCAL: Python worker on the user's GPU        │ │
                   │                                     │ CLOUD: Opus over WebRTC to Voxlate GPU server │ │
                   │                                     └───────────────────────────────────────────────┘ │
                   │                       translated audio ─► Output mixer (mute, fail-closed, no leak)  │
                   └────────────────────────────────────────────────────────────────────┬────────────────┘
                                                                                        ▼
                                                    VB-CABLE: CABLE Input ─► CABLE Output = mic in Meet / Zoom / Teams
```

- **Local engine** (exists today): everything runs on the user's PC. Free tier and privacy option. Needs an NVIDIA GPU with 4 GB or more; quality is limited by the hardware.
- **Cloud engine** (to build): the desktop app becomes a thin client. All AI runs on the server, which allows bigger models, all languages and lower latency on any PC.
- **Always on the PC, both modes:** mic capture, VAD (silence never leaves the PC), the safety mixer and VB-CABLE output. If the network drops, the cable goes **silent** (fail-closed).

---

## 2. The pipeline, stage by stage

| # | Stage | What it does | Local engine (today) | Cloud engine (target) |
|---|---|---|---|---|
| 1 | Capture | 20 ms timestamped mic frames | WASAPI (PortAudio) | same, on the PC |
| 2 | VAD | Detects speech start/end, drops silence | Silero VAD | same, on the PC (saves bandwidth) |
| 3 | Transport | — | — | WebRTC, Opus ~24–32 kbps each way |
| 4 | Language ID | Source language | user-selected | user-selected, or Whisper language ID |
| 5 | ASR | Speech → text, streamed | faster-whisper large-v3-turbo | routed per language (see §3.1) |
| 6 | Segmenter | Cuts at sentence or clause ends, keeps context | rule-based (Hindi verb-final) | same, plus LLM-aware sentence end |
| 7 | MT | Text → target language | IndicTrans2 200M distilled | routed per pair; LLM with context (§3.2) |
| 8 | TTS + clone | Target text → speech in the user's voice | Kokoro-82M + OpenVoice V2 | Chatterbox Multilingual / OmniVoice (§3.3) |
| 9 | Return | Audio chunks streamed back | — | WebRTC |
| 10 | Mixer | Translated only / original / both, mute, backlog bound | on the PC | on the PC |
| 11 | Output | Plays into VB-CABLE | CABLE Input | CABLE Input |

**Latency budget (cloud, after the speaker finishes a sentence, estimated):** network 50–150 ms + end-of-speech 250 ms + ASR 100–200 ms + MT 150–400 ms + TTS first chunk 150–300 ms ≈ **0.8–1.5 s**. Measured today on the local engine: ~10–13 s. Most of that is pipeline waiting, which the planned fixes remove. Verb-final languages (Hindi, Japanese, Korean, Turkish…) add the time until the verb is spoken.

**Voice profile:** a 30–60 s consented recording becomes a speaker embedding. Local: DPAPI-encrypted on the PC. Cloud: store only the embedding plus a consent record, encrypted per user, deletable on request.

---

## 3. Models cleared for commercial use

### 3.1 Speech recognition (ASR)
| Model | Licence | Languages | Use in Voxlate |
|---|---|---|---|
| OpenAI Whisper large-v3 / large-v3-turbo (via faster-whisper, CTranslate2) | MIT | ~99 | **Default ASR**, local and cloud |
| Meta Omnilingual ASR (300M–7B) | Apache-2.0 | 1,600+ | Long-tail languages, cloud (streaming support unconfirmed) |
| AI4Bharat IndicConformer (NeMo) | **verify** | 22 Indian | Indian languages, best accuracy |
| NVIDIA Parakeet-TDT / Canary | CC-BY-4.0 | English + ~25 European | Optional low-latency path for EU languages |
| Sherpa-ONNX (k2-fsa) runtime | Apache-2.0 | — | Streaming inference engine (C++ core, Python API) |
| Silero VAD | MIT | language-independent | VAD on the PC |

### 3.2 Translation (MT)
| Model | Licence | Languages | Use in Voxlate |
|---|---|---|---|
| Qwen3 LLM (e.g. 30B-A3B MoE via vLLM) | Apache-2.0 (**verify** per checkpoint) | ~100+ | **Default cloud MT**: context-aware, best grammar |
| Google TranslateGemma 4B / 12B / 27B | Gemma Terms of Use (commercial use allowed, with usage policy) | 55 | Alternative specialist MT |
| Google MADLAD-400 3B / 7B | Apache-2.0 | 400+ | Long-tail fallback ("not assessed for production" per Google) |
| AI4Bharat IndicTrans2 1B / 200M | MIT | 22 Indian | Indian pairs; local engine default |

### 3.3 Speech synthesis and voice cloning (TTS)
| Model | Licence | Languages | Use in Voxlate |
|---|---|---|---|
| Resemble AI Chatterbox Multilingual | MIT | 23 (incl. Hindi; Hindi fine-tune available) | **Default cloud TTS**, zero-shot clone from ~5 s |
| k2-fsa OmniVoice | code Apache-2.0, weights **verify** | 600+ | Long-tail languages |
| Alibaba Qwen3-TTS | Apache-2.0 | 10 | Alternative for major languages |
| Kokoro-82M | Apache-2.0 | ~9 (incl. Hindi) | Local engine TTS |
| MyShell OpenVoice V2 (tone converter) | MIT | language-independent | Local engine voice conversion |
| Fish Audio S1 / S2 | **paid licence only** (open weights under research licence) | — | Optional premium: hosted API ≈ $15 per 1M text bytes, or self-host enterprise ≈ $10k/month (≈ $120–150k/yr floor) |

### 3.4 Infrastructure software (all commercial-friendly)
LiveKit (Apache-2.0) for WebRTC · vLLM (Apache-2.0) for LLM serving · CTranslate2 (MIT) · ONNX Runtime (MIT) · PyTorch (BSD-3) · Qt 6 (LGPL-3, dynamically linked) · VB-CABLE (donationware; **user-installed, not bundled**, since redistribution needs a VB-Audio licence).

### 3.5 Excluded (non-commercial)
XTTS-v2 (Coqui CPML), F5-TTS weights, Fish Speech open weights (CC-BY-NC-SA / research licence), NLLB-200 and SeamlessM4T / SeamlessStreaming (CC-BY-NC). Higgs Audio is reported as research-only. Pyannote is MIT but **not needed**: one speaker per stream. Use speaker verification against the enrolled voice instead.

---

## 4. Server specs

### 4.1 One inference node (starting point)
| Item | Spec |
|---|---|
| GPU | 1× NVIDIA **L40S 48 GB** (or A100 80 GB for headroom) |
| Models resident | Whisper large-v3-turbo (~2 GB) + Qwen3-30B-A3B in int4 / AWQ (~17–20 GB) + Chatterbox (~3–4 GB) + IndicTrans2 1B int8 (~1.5 GB) ≈ 25–30 GB VRAM |
| CPU / RAM | 16 vCPU / 64 GB |
| Disk | 200 GB NVMe (models ~60 GB) |
| Network | 1 Gbps; ~25–30 kbps per direction per stream |
| **Capacity (estimate, to load-test)** | **~8–15 concurrent live streams**. Speech is bursty: people talk about 40–50% of a call. |

### 4.2 Production layout
- **Region:** start in India (e.g. AWS ap-south-1 Mumbai, or an India GPU provider) for users there, since round-trip time drives latency. Add regions as users grow.
- **Topology:** a WebRTC edge (LiveKit) → session router → GPU inference nodes (autoscaled; minimum 2 for redundancy) → Postgres (accounts, usage minutes, consent) + object store (encrypted voice embeddings).
- **Scaling rule:** add a GPU node per ~10 concurrent streams at peak (refine after load tests).
- **Observability:** per-stage latency (p50/p95), GPU utilisation, stream failures. Never log audio or transcripts.

### 4.3 GPU prices (on-demand, USD per GPU-hour, 2026 public listings)
| GPU | Budget clouds (RunPod / Lambda class) | AWS |
|---|---|---|
| L4 24 GB | ~$0.44–0.80 | g6.xlarge ≈ $0.97 (Mumbai), $0.80 (us-east-1) |
| **L40S 48 GB** | **~$0.86–1.09** | g6e.xlarge ≈ $1.86 (us-east-1); g6e.4xlarge ≈ $3.61 (Mumbai) |
| A100 80 GB | ~$1.39–1.99 | p4de ≈ $3.43 per GPU |
| H100 80 GB | ~$2.49–4.29 | ≈ $6.88 per GPU |

Reserved or savings-plan pricing is typically 30–60% lower; spot is lower still but can be interrupted (avoid for live calls).

---

## 5. Cost per user-hour (estimate)

Assumptions: an L40S node serving **10** concurrent streams on average at busy times, with **+30% overhead** (redundancy, CPU, storage, idle capacity, bandwidth). Bandwidth is ~25 MB per user-hour, so ~$0.002 at $0.09/GB egress (negligible).

| Scenario | Node $/hr | ÷ 10 streams | +30% overhead | **Cost per translated user-hour** |
|---|---|---|---|---|
| Budget cloud (L40S ~$0.95) | $0.95 | $0.095 | $0.12 | **≈ $0.12 (₹10)** |
| AWS us-east-1 (g6e.xlarge) | $1.86 | $0.186 | $0.24 | **≈ $0.24 (₹21)** |
| AWS Mumbai (g6e.4xlarge) | $3.61 | $0.361 | $0.47 | **≈ $0.47 (₹41)** |
| Fish Audio API for TTS (alternative) | — | — | — | adds ≈ $0.10–0.20 per hour of speech (≈ 7–13k chars/hour) |

Fixed monthly baseline (2 always-on nodes for availability, plus small CPU services and database): about **$1.4k (budget cloud) to $5.5k (AWS Mumbai)**.

**Break-even:** at ₹1,499/month Pro with ~14 hours used, revenue minus GST and payment fees is ≈ ₹1,230 (~$14); usage cost is ₹140–575. Each Pro user contributes ≈ ₹1,090 (~$12.5) on budget cloud or ≈ ₹655 (~$7.5) on AWS Mumbai. So the platform baseline is covered by roughly **110 Pro users (budget cloud) to 730 (AWS Mumbai on-demand)**. That's another reason to start on budget or reserved GPUs.

---

## 6. Subscription model (proposal)

Billing by **translated minutes**: time the cloud engine actually processes speech, not call length.

| Plan | Price (India) | Price (global) | Includes | Who |
|---|---|---|---|---|
| **Free (Local)** | ₹0 | $0 | Unlimited **local engine** (own NVIDIA GPU), Hindi ↔ English + Indian languages; 60 cloud minutes/month trial | Students, try-before-buy |
| **Starter** | ₹499/mo | $7/mo | 10 cloud hours, all languages, voice clone | Occasional calls |
| **Pro** | ₹1,499/mo | $19/mo | 40 cloud hours, priority routing, custom glossary | Freelancers, sales, daily meetings |
| **Business** (per seat) | ₹3,999/mo | $49/mo | 120 hours pooled per seat, admin console, usage reports, SSO | Teams |
| **Enterprise** | custom | custom | Dedicated GPUs / VPC / on-prem, data residency, SLA, DPA | Regulated orgs |
| Top-up | ₹99 per 2 h | $1.50 per 2 h | Extra cloud hours | All paid plans |

**Margin check (Pro, expected use ~35% of cap = 14 h):** cost ₹140–575 (budget cloud to AWS Mumbai) against net revenue ≈ ₹1,230 gives **gross margin ≈ 55–90%**. A heavy user at the full 40 h on AWS Mumbai costs ≈ ₹1,640, which is a loss. So run on budget or reserved GPUs and enforce the caps. Annual plans at ~2 months free improve cash flow.

**Indian pricing notes:** the ₹ prices **include** 18% GST (₹1,499 → ₹1,270 before tax). Payment gateway fees are ~2–3% (Razorpay / Stripe), leaving ≈ ₹1,230 net for Pro. Rupee figures assume ≈ ₹85–90 per US$.

---

## 7. Legal and compliance checklist
- Explicit, logged consent for voice cloning; users may clone **only their own voice**. Add an audible or visible "AI-translated" disclosure option for meetings.
- India DPDP Act 2023 (consent, purpose limitation, deletion on request); GDPR if serving the EU.
- Keep a model licence register (this document) and re-check licences whenever a model version changes.
- VB-CABLE: users install it themselves, or negotiate a redistribution licence with VB-Audio. Longer term: a signed virtual audio driver of our own.

## 8. Next steps
1. Finish the local-engine latency work (pipeline fixes, measured per stage).
2. Build a cloud prototype on one L40S: Whisper turbo + Qwen3-30B-A3B + Chatterbox, LiveKit transport.
3. Load-test for real concurrent streams per GPU and replace the estimates in §4–§6.
4. Native-speaker quality rating for the top 5–10 languages; confirm all **verify** licences.
5. Pilot with ~20 users on Free and Pro before fixing prices.

---

## Sources
- GPU prices: [Spheron – RunPod vs Lambda 2026](https://www.spheron.network/blog/runpod-vs-lambda-labs-2026/), [Spheron – GPU cloud pricing 2026](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/), [CloudZero – cloud GPU pricing](https://www.cloudzero.com/blog/cloud-gpu-pricing-comparison/), [ManagedModels – A100/H100/L40S](https://managedmodels.com/hosting/gpu-cloud-pricing-compared/), [BuildMVPFast – GPU cloud costs](https://www.buildmvpfast.com/blog/gpu-cloud-cost-comparison-runpod-lambda-labs-coreweave-2026), [DevZero – g6e.xlarge](https://www.devzero.io/instances/aws/g6e.xlarge), [DevZero – g6e.4xlarge](https://www.devzero.io/instances/aws/g6e.4xlarge), [DoiT – g6.xlarge ap-south-1](https://www.doit.com/compute/spot/ap-south-1/g6.xlarge), [DoiT – g6.4xlarge ap-south-1](https://www.doit.com/compute/spot/ap-south-1/g6.4xlarge)
- Fish Audio: [developers / pricing](https://fish.audio/en/developers/), [S2 licence explainer](https://fish.audio/fr/blog/what-we-mean-by-open-source-for-s2/), [fish-speech on PyPI](https://pypi.org/project/fish-speech/)
- TTS: [Chatterbox model card](https://huggingface.co/ResembleAI/chatterbox/blob/main/README.md), [Resemble – Chatterbox Multilingual](https://resemble.ai/learn/models/chatterbox-multilingual), [k2-fsa OmniVoice](https://github.com/k2-fsa/OmniVoice), [Qwen3-TTS guide](https://dev.to/czmilo/qwen3-tts-the-complete-2026-guide-to-open-source-voice-cloning-and-ai-speech-generation-1in6), [Open-source TTS 2026 roundup](https://pinggy.io/blog/best_open_source_self_hosted_text_to_speech_models/)
- ASR: [Meta Omnilingual ASR paper](https://arxiv.org/pdf/2511.09690), [The Decoder – Omnilingual ASR](https://the-decoder.com/metas-omnilingual-asr-brings-speech-recognition-to-1600-languages/)
- MT: [InfoQ – TranslateGemma](https://www.infoq.com/news/2026/01/google-translategemma-models), [TranslateGemma guide](https://aicybr-sveltekit.pages.dev/blog/translategemma-guide), [MADLAD-400 3B card](https://huggingface.co/google/madlad400-3b-mt/raw/main/README.md), [MADLAD-400 7B card](https://huggingface.co/google/madlad400-7b-mt/raw/main/README.md)
