"""
mps_cuda_patch.py

Applies (or reverts) the CLaRa CUDA<->MPS compatibility patch to
modeling_clara.py.

Why a script instead of a `.patch` file: the real patched file lives only
inside the HuggingFace transformers_modules cache on the Mac Studio
(~/.cache/huggingface/modules/transformers_modules/compression-16/modeling_clara.py)
-- it was never checked into this repo, and nobody working in this session
has read access to it. A hand-authored unified diff would mean guessing at
line numbers and surrounding context in a file nobody here has actually
seen -- worse than not having a patch at all, since it could silently fail
to apply or (worse) apply somewhere wrong. This script instead encodes the
patch as a small set of literal text substitutions -- the same ones already
documented in CLAUDE.md's "MPS Patches" section -- and can run in either
direction against whatever the real file's current content actually is.

Two directions:
  --to-cuda   MPS -> CUDA   (what production Linux+NVIDIA needs at cutover)
  --to-mps    CUDA -> MPS   (what the Mac Studio dev setup needs, e.g. after
                             a fresh `from_pretrained(..., trust_remote_code=True)`
                             re-download resets the cached module to its
                             original CUDA-only form)

Usage:
    # Preview only (default) -- prints a unified diff, changes nothing
    python patches/mps_cuda_patch.py --to-cuda

    # Actually apply, writing a .bak backup alongside the target first
    python patches/mps_cuda_patch.py --to-cuda --apply

    # Target a different file than the documented default
    python patches/mps_cuda_patch.py --to-cuda --apply --file /path/to/modeling_clara.py

    # Prove the substitution logic is correct without touching any real
    # file (useful when verifying this script from a machine that doesn't
    # have modeling_clara.py at all, like a Mac Mini with no Mac Studio access)
    python patches/mps_cuda_patch.py --demo --to-cuda

This script does NOT handle two things documented in CLAUDE.md that need a
separate manual step -- see patches/README.md:
  1. bfloat16 vs float16 -- an optional performance choice, not a strict
     compatibility requirement, so it's not auto-applied here.
  2. PYTORCH_ENABLE_MPS_FALLBACK=1 -- an environment variable set on the Mac
     Studio's LaunchDaemon, not a line inside this source file.
"""
import argparse
import difflib
import sys
from pathlib import Path

DEFAULT_TARGET = Path(
    "~/.cache/huggingface/modules/transformers_modules/compression-16/modeling_clara.py"
).expanduser()

# Each rule is (mps_form, cuda_form). --to-cuda replaces mps_form -> cuda_form;
# --to-mps replaces cuda_form -> mps_form. Listed in the same order CLAUDE.md
# documents them.
RULES = [
    (".to('mps')", ".to('cuda')"),
    ('.to("mps")', '.to("cuda")'),
    ("torch.backends.mps.is_available()", "torch.cuda.is_available()"),
    ("torch.mps.empty_cache()", "torch.cuda.empty_cache()"),
]

DEMO_MPS_SNIPPET = '''\
import torch

class ClaraModel:
    def to_device(self):
        if torch.backends.mps.is_available():
            self.model = self.model.to('mps')
        return self.model

    def clear_cache(self):
        torch.mps.empty_cache()
'''


def apply_rules(text: str, direction: str) -> str:
    for mps_form, cuda_form in RULES:
        if direction == "to-cuda":
            text = text.replace(mps_form, cuda_form)
        else:  # to-mps
            text = text.replace(cuda_form, mps_form)
    return text


def print_diff(before: str, after: str, path: str):
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"{path} (before)",
        tofile=f"{path} (after)",
    )
    sys.stdout.writelines(diff)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    direction_group = parser.add_mutually_exclusive_group(required=True)
    direction_group.add_argument("--to-cuda", action="store_true", help="Revert MPS patch -> CUDA (production)")
    direction_group.add_argument("--to-mps", action="store_true", help="Apply CUDA -> MPS patch (Mac Studio dev)")
    parser.add_argument("--file", default=str(DEFAULT_TARGET), help="Target file (default: documented HF cache path)")
    parser.add_argument("--apply", action="store_true", help="Write changes in place (default: dry-run, prints diff only)")
    parser.add_argument("--demo", action="store_true", help="Run against a built-in sample snippet instead of --file, to verify the substitution logic with no real file present")
    args = parser.parse_args()

    direction = "to-cuda" if args.to_cuda else "to-mps"

    if args.demo:
        before = DEMO_MPS_SNIPPET if direction == "to-cuda" else apply_rules(DEMO_MPS_SNIPPET, "to-cuda")
        after = apply_rules(before, direction)
        print(f"[demo] direction={direction}\n")
        print_diff(before, after, "demo_snippet.py")
        if before == after:
            print("\n[demo] No changes -- substitution rules did not match the demo snippet (this would be a bug).", file=sys.stderr)
            sys.exit(1)
        print("\n[demo] Substitution logic verified OK.")
        return

    target = Path(args.file).expanduser()
    if not target.exists():
        print(
            f"File not found: {target}\n"
            "This script must be run on the machine where modeling_clara.py actually "
            "lives (currently the Mac Studio's HuggingFace cache), or pointed at a "
            "local copy via --file. Use --demo to verify the substitution logic "
            "without a real file.",
            file=sys.stderr,
        )
        sys.exit(1)

    before = target.read_text()
    after = apply_rules(before, direction)

    if before == after:
        print(f"No changes needed -- {target} already matches the '{direction}' target state (or contains none of the known patterns).")
        return

    print_diff(before, after, str(target))

    if args.apply:
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_text(before)
        target.write_text(after)
        print(f"\nApplied. Backup written to {backup}")
    else:
        print("\nDry run only -- no files changed. Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
