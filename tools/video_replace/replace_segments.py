#!/usr/bin/env python3
"""
把影片中「真人講解」的片段換成球員圖片（保留原音軌、原解析度）。

用法:
  python3 replace_segments.py --video in.mp4 --plan plan.json --out out.mp4

plan.json 格式:
{
  "segments": [
    {"start": 3.2, "end": 9.8, "image": "assets/durant.jpg", "caption": "Kevin Durant / 火箭"},
    {"start": 25.0, "end": 31.5, "image": "assets/sengun.jpg"}
  ],
  "credits": "照片：Wikimedia Commons（CC BY 4.0，Houston Roundball Review）"
}
圖片會以「模糊放大背景 + 置中縮放」填滿 9:16 畫面，並加上輕微 Ken Burns 推移；
caption 以半透明底條顯示；credits 於片尾 3 秒疊字。
"""
import argparse, json, subprocess, shlex, os, sys

def probe(video):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate:format=duration",
        "-of", "json", video])
    d = json.loads(out)
    s = d["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), float(d["format"]["duration"])

def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", default="/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
    a = ap.parse_args()

    W, H, fps, dur = probe(a.video)
    plan = json.load(open(a.plan, encoding="utf-8"))
    segs = sorted(plan["segments"], key=lambda s: s["start"])

    inputs = ["-i", a.video]
    fc = []
    for i, s in enumerate(segs, start=1):
        length = s["end"] - s["start"]
        inputs += ["-i", s["image"]]  # 單張圖，由 zoompan 產生 frames 張
        frames = int(length * fps) + 1
        # 背景：模糊放大；前景：等比縮放置中 + Ken Burns 緩慢推近
        fc.append(
            f"[{i}:v]split[bg{i}][fg{i}];"
            f"[bg{i}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=30,eq=brightness=-0.15[bgo{i}];"
            f"[fg{i}]scale={W}:{H}:force_original_aspect_ratio=decrease[fgo{i}];"
            f"[bgo{i}][fgo{i}]overlay=(W-w)/2:(H-h)/2[comp{i}];"
            f"[comp{i}]zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps},"
            f"trim=duration={length:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[img{i}]"
        )
        if s.get("caption"):
            fc[-1] = fc[-1][:-len(f"[img{i}]")] + (
                f",drawbox=x=0:y=ih-170:w=iw:h=120:color=black@0.55:t=fill,"
                f"drawtext=fontfile='{a.font}':text='{esc(s['caption'])}':fontsize=46:fontcolor=white:"
                f"x=(w-text_w)/2:y=h-150[img{i}]"
            )

    # 把主影片依 segments 切成「保留 / 替換」交錯串接
    parts, cursor = [], 0.0
    for i, s in enumerate(segs, start=1):
        if s["start"] > cursor + 0.02:
            fc.append(f"[0:v]trim=start={cursor:.3f}:end={s['start']:.3f},setpts=PTS-STARTPTS[keep{i}]")
            parts.append(f"[keep{i}]")
        parts.append(f"[img{i}]")
        cursor = s["end"]
    if cursor < dur - 0.02:
        fc.append(f"[0:v]trim=start={cursor:.3f}:end={dur:.3f},setpts=PTS-STARTPTS[keepend]")
        parts.append("[keepend]")
    fc.append("".join(parts) + f"concat=n={len(parts)}:v=1:a=0[vcat]")

    last = "[vcat]"
    if plan.get("credits"):
        fc.append(
            f"{last}drawtext=fontfile='{a.font}':text='{esc(plan['credits'])}':fontsize=28:fontcolor=white@0.9:"
            f"box=1:boxcolor=black@0.5:boxborderw=12:x=(w-text_w)/2:y=h-80:enable='gte(t,{max(dur-3,0):.2f})'[vout]")
        last = "[vout]"

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
           "-map", last, "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-c:a", "copy", "-movflags", "+faststart", "-shortest", a.out]
    print(" ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
    subprocess.check_call(cmd)

if __name__ == "__main__":
    main()
