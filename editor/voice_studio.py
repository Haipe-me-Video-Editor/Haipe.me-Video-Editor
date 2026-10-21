"""Resemble Enhance (MIT): AI denoise + studio restoration of a voice track, in its own venv.

Launched by editor.voice.studio_restore. It beat every ffmpeg chain in blind A/B listening.
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lambd", type=float, default=0.9)  # denoise strength before the enhancer
    ap.add_argument("--nfe", type=int, default=64)
    a = ap.parse_args()

    import soundfile as sf
    import torch
    from resemble_enhance.enhancer.inference import enhance

    torch.set_num_threads(max(1, torch.get_num_threads()))
    audio, sr = sf.read(a.wav, dtype="float32")
    wav = torch.from_numpy(audio if audio.ndim == 1 else audio.mean(1))
    out, out_sr = enhance(wav, sr, "cpu", nfe=a.nfe, solver="midpoint", lambd=a.lambd, tau=0.5)
    sf.write(a.out, out.cpu().numpy(), out_sr)


if __name__ == "__main__":
    main()
