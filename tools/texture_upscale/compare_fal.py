"""Run a small, budgeted FAL Clarity comparison on local texture PNGs."""

import argparse
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

ENDPOINT = "fal-ai/clarity-upscaler"
PROMPT = (
    "Faithful restoration of a hand-painted video game texture. Sharpen existing "
    "lines and recover fine material detail. Preserve the exact colors, shapes, "
    "layout, lighting, and every object boundary. This is a flat UV texture, "
    "not a new scene. No new objects, words, highlights, or shadows."
)


def load_key(path):
    key = os.environ.get("FAL_KEY")
    if key:
        return key
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if line.startswith("FAL_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("Set FAL_KEY locally. Do not put it in source or reports.")


def request(url, key, data=None):
    if not url.startswith(("https://queue.fal.run/", "https://api.fal.ai/")):
        raise RuntimeError("Unexpected FAL API URL")
    headers = {"Authorization": "Key " + key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    body = json.dumps(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, body, headers), timeout=60
        ) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"FAL request failed with HTTP {error.code}. No automatic retry."
        ) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not 0 < args.budget <= 10:
        parser.error("Use an explicitly approved budget up to $10.")
    args.output.mkdir(parents=True, exist_ok=True)
    key = load_key(args.env_file)
    price = request("https://api.fal.ai/v1/models/pricing?endpoint_id=" + ENDPOINT, key)
    record = price["prices"][0]
    if record["currency"] != "USD" or record["unit"] != "megapixels":
        raise RuntimeError(
            "Review the changed billing unit before running comparisons."
        )
    unit_price = float(record["unit_price"])
    ledger_path = args.output / "ledger.json"
    if ledger_path.exists():
        raise RuntimeError("Use a new comparison directory to avoid duplicate charges.")
    ledger = {
        "endpoint": ENDPOINT,
        "price": record,
        "budget_usd": args.budget,
        "requests": [],
    }
    reserved = 0.0
    for path in args.images:
        with Image.open(path) as source:
            # A small comparison cannot consume the whole pack's API budget.
            if max(source.size) > 512:
                raise RuntimeError(
                    "Comparison inputs must be at most 512 pixels per edge."
                )
            input_size = source.size
        for creativity in (0.15, 0.35):
            reserve = max(
                0.25,
                unit_price * max(1, input_size[0] * input_size[1] * 16 / 1_000_000) * 2,
            )
            if reserved + reserve > args.budget:
                raise RuntimeError("The comparison would exceed its reserved budget.")
            reserved += reserve
            name = path.stem + f"-clarity-{creativity:.2f}.png"
            item = {
                "input": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "creativity": creativity,
                "reserved_usd": reserve,
                "output": name,
                "status": "reserved",
                "input_size": input_size,
                "prompt": PROMPT,
            }
            ledger["requests"].append(item)
            ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
            data_url = (
                "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
            )
            submitted = request(
                "https://queue.fal.run/" + ENDPOINT,
                key,
                {
                    "image_url": data_url,
                    "upscale_factor": 4,
                    "prompt": PROMPT,
                    "negative_prompt": "new objects, changed layout, changed colors, invented text, blur, halos",
                    "creativity": creativity,
                    "resemblance": 1.0,
                    "guidance_scale": 4,
                    "num_inference_steps": 18,
                    "seed": 20260908,
                },
            )
            item.update(request_id=submitted["request_id"], status="submitted")
            ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
            print(
                f"FAL comparison {path.name}, creativity {creativity}, reserved ${reserved:.2f}",
                flush=True,
            )
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                current = request(submitted["status_url"], key)
                if current["status"] == "COMPLETED":
                    break
                time.sleep(1)
            else:
                raise RuntimeError(
                    "Comparison did not complete in five minutes. Check its request ID."
                )
            result = request(submitted["response_url"], key)
            image = result["image"]
            if not image["url"].startswith("https://"):
                raise RuntimeError("Unexpected output image URL")
            with urllib.request.urlopen(image["url"], timeout=60) as response:
                (args.output / name).write_bytes(response.read())
            item.update(
                status="completed",
                output_size=[image["width"], image["height"]],
                timings=result.get("timings"),
                seed=result.get("seed"),
            )
            ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    print(
        f"Completed {len(ledger['requests'])} comparisons. Reserved at most ${reserved:.2f}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
