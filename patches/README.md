# CLaRa MPS <-> CUDA patch

## Why this directory exists

CLaRa's `modeling_clara.py` was patched to run on Apple MPS (for dev on the Mac Studio's M3 Ultra) instead of CUDA. That patch has always lived only inside the HuggingFace `transformers_modules` cache on the Mac Studio (`~/.cache/huggingface/modules/transformers_modules/compression-16/modeling_clara.py`) — never in git. A fresh `from_pretrained(..., trust_remote_code=True)` re-download would silently wipe it, and the eventual production cutover (single Linux+NVIDIA server, per CLAUDE.md — not yet provisioned) would otherwise depend on someone re-deriving the same edits from memory.

`mps_cuda_patch.py` is a substitute for a checked-in `.patch` file. Nobody working on this repo from this machine has read access to the real file on the Mac Studio, so a hand-authored unified diff would be guessing at content nobody here has verified — worse than nothing, since it could silently fail to apply, or apply in the wrong place. This script instead encodes the patch as literal text substitutions and can be run in either direction against whatever the real file's current content actually is.

## What it automates

| Change | Handled by script |
|---|---|
| `.to('mps')` / `.to("mps")` ↔ `.to('cuda')` / `.to("cuda")` | Yes |
| `torch.backends.mps.is_available()` ↔ `torch.cuda.is_available()` | Yes |
| `torch.mps.empty_cache()` ↔ `torch.cuda.empty_cache()` | Yes |

## What it does NOT automate (do these manually)

1. **bfloat16 vs float16.** CLAUDE.md notes bfloat16 *can* replace float16 on CUDA — this is an optional performance choice, not a strict compatibility requirement (float16 still works on CUDA), so the script deliberately doesn't touch dtype literals. Review dtype usage by hand if you want this optimization.
2. **`PYTORCH_ENABLE_MPS_FALLBACK=1`.** This is an environment variable set on the Mac Studio's CLaRa LaunchDaemon (`com.nutribot.clara`), not a line inside `modeling_clara.py`. Remove it from that LaunchDaemon's plist (or launch environment) when cutting over to production — there's nothing in this source file for the script to change.

## Usage

Run this **on the machine where `modeling_clara.py` actually lives** — currently the Mac Studio (or on a fresh copy downloaded to whatever machine is being prepared for production):

```bash
# Preview only (default) -- prints a unified diff, changes nothing
python patches/mps_cuda_patch.py --to-cuda

# Actually apply, writes a .bak backup alongside the target first
python patches/mps_cuda_patch.py --to-cuda --apply

# Target a different file than the documented default cache path
python patches/mps_cuda_patch.py --to-cuda --apply --file /path/to/modeling_clara.py

# Reverse direction -- e.g. after a fresh HF cache re-download resets the
# file back to its original CUDA-only form, and the Mac Studio needs MPS again
python patches/mps_cuda_patch.py --to-mps --apply
```

### Verifying the script itself

`--demo` runs the same substitution logic against a built-in sample snippet instead of a real file — this is how the script was verified in a session that had no access to the actual Mac Studio file:

```bash
python patches/mps_cuda_patch.py --demo --to-cuda
python patches/mps_cuda_patch.py --demo --to-mps
```

## Production cutover checklist

1. Copy (or freshly download) `modeling_clara.py` to the production Linux+NVIDIA box.
2. Run `python patches/mps_cuda_patch.py --to-cuda --apply --file <path>`.
3. Remove `PYTORCH_ENABLE_MPS_FALLBACK=1` from the production launch environment (item #2 above).
4. Optionally review float16 → bfloat16 (item #1 above).
5. Set `USE_CLARA_COMPRESS`/`USE_CLARA`/`OLLAMA_BASE_URL`/etc. in `.env` to point at the new box, per CLAUDE.md's Environment Variables section.
6. Smoke-test with `eval/test_rag.py --smoke` before cutting the public URL over.
