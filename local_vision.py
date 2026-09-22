"""
Local vision-language agent (Qwen2-VL-2B-Instruct by default) that runs on the server GPU with no
API key. Used as the second helmet agent: it takes over when the cloud agent (Gemini / Claude) is
missing, out of credits or rate-limited, and it gives a second opinion on demand from the helmet page.

    LOCAL_VLM=Qwen/Qwen2-VL-2B-Instruct   # HF model id (default); ~4.4 GB download on first start
    LOCAL_VLM=0                            # disable

The model loads lazily in a background thread so the server starts without waiting for it. fp16 on
CUDA needs ~5 GB VRAM next to the YOLO26x detector; on CPU it still works but takes ~20 s per image.
"""
import io
import os
import threading
import time

MODEL_ID = os.getenv("LOCAL_VLM", "Qwen/Qwen2-VL-2B-Instruct")
MAX_PIXELS = 512 * 512          # crops are small; capping the vision tokens keeps a query ~1 s


class LocalVisionAgent:
    name = "local-vlm"

    def __init__(self, model_id=MODEL_ID):
        self.model_id = model_id
        self.enabled = model_id not in ("", "0", "off", "none")
        self.model = None
        self.processor = None
        self.device = "cpu"
        self.error = None
        self.loading = False
        self._lock = threading.Lock()
        self.name = model_id.split("/")[-1].lower() if self.enabled else "off"
        if self.enabled:
            threading.Thread(target=self.load, daemon=True).start()

    # ------------------------------------------------------------ lifecycle
    def load(self):
        with self._lock:
            if self.model is not None or self.error or not self.enabled:
                return
            self.loading = True
            t0 = time.time()
            try:
                import torch
                from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                dtype = torch.float16 if self.device == "cuda" else torch.float32
                self.processor = AutoProcessor.from_pretrained(self.model_id, min_pixels=64 * 64, max_pixels=MAX_PIXELS)
                self.model = Qwen2VLForConditionalGeneration.from_pretrained(self.model_id, dtype=dtype, device_map=self.device)
                self.model.eval()
                print(f"[LocalVLM] {self.model_id} ready on {self.device} in {time.time() - t0:.0f}s")
            except Exception as e:  # noqa: BLE001 - a missing model must not stop the server
                self.error = f"{type(e).__name__}: {str(e)[:200]}"
                print(f"[LocalVLM] failed to load {self.model_id}: {self.error}")
            finally:
                self.loading = False

    def ready(self):
        return self.model is not None

    def status(self):
        return {"model": self.model_id if self.enabled else None, "ready": self.ready(), "loading": self.loading,
                "device": self.device, "error": self.error}

    # ------------------------------------------------------------ query
    def ask(self, jpeg, system, prompt, max_new_tokens=160):
        """Run one image + prompt through the model. Raises RuntimeError when the model is not ready."""
        if not self.ready():
            self.load()
        if not self.ready():
            raise RuntimeError(self.error or "local vision model still loading")
        import torch
        from PIL import Image
        image = Image.open(io.BytesIO(jpeg)).convert("RGB")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]},
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[image], return_tensors="pt").to(self.device)
        with self._lock, torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        trimmed = out[:, inputs["input_ids"].shape[1]:]
        return self.processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=True)[0].strip()
