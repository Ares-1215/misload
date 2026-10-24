#!/usr/bin/env python3
"""
compose.py — 一次完成：去浮水印/去 logo、圓形小視窗換成球員頭像、
主持人全畫面片段換成球員照片（重繪字幕）、裁掉片尾、加出處。保留原音軌。

用法: python3 compose.py plan.json
plan.json 欄位見 README 或 plan 範例。
"""
import json, subprocess, shlex, sys, os
import cv2, numpy as np

FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

def esc(t):
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%").replace(",", "\\,")

def probe(video):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "json", video])
    d = json.loads(out); s = d["streams"][0]; num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num)/float(den), float(d["format"]["duration"])

def make_circle(img_path, cx, cy, size, r, out_path, ring=4):
    """從照片裁正方形（中心 cx,cy、邊長 size 皆為寬度比例），做成直徑 2r 的圓形 PNG，白色外框。"""
    img = cv2.imread(img_path, cv2.IMREAD_COLOR)
    H, W = img.shape[:2]
    side = int(size * W); x0 = int(cx * W - side/2); y0 = int(cy * H - side/2)
    # 邊界處理：不足的地方用邊緣延伸
    pad = max(0, -x0, -y0, x0+side-W, y0+side-H)
    if pad:
        img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REPLICATE); x0 += pad; y0 += pad
    crop = img[y0:y0+side, x0:x0+side]
    d = 2*r
    crop = cv2.resize(crop, (d, d), interpolation=cv2.INTER_AREA)
    yy, xx = np.mgrid[:d, :d]; dist = np.sqrt((xx-r+0.5)**2 + (yy-r+0.5)**2)
    alpha = np.clip(r - dist + 0.5, 0, 1)                      # 抗鋸齒圓形
    ringmask = np.clip(r - dist + 0.5, 0, 1) * np.clip(dist - (r-ring) + 0.5, 0, 1)
    bgra = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA).astype(np.float32)
    for c in range(3):
        bgra[..., c] = bgra[..., c]*(1-ringmask) + 255*ringmask
    bgra[..., 3] = alpha*255
    cv2.imwrite(out_path, bgra.astype(np.uint8))

def main():
    plan = json.load(open(sys.argv[1], encoding="utf-8"))
    video, out = plan["video"], plan["out"]
    W, H, fps, dur = probe(video)
    end = float(plan.get("end", dur))
    tmp = plan.get("tmpdir", os.path.dirname(os.path.abspath(out)))
    os.makedirs(tmp, exist_ok=True)

    inputs = ["-i", video]
    fc = []
    # ---- 1. 基底：裁長度、去浮水印/去 logo ----
    chain = f"[0:v]trim=0:{end:.3f},setpts=PTS-STARTPTS"
    for b in plan.get("delogo", []):
        chain += f",delogo=x={b['x']}:y={b['y']}:w={b['w']}:h={b['h']}"
        if b.get("enable"): chain += f":enable='{b['enable']}'"
    chain += "[b0]"; fc.append(chain)
    # ---- 2. 圓形小視窗覆蓋 ----
    cur = "[b0]"
    for i, p in enumerate(plan.get("pip", [])):
        png = os.path.join(tmp, f"circle_{i}.png")
        make_circle(p["image"], p["cx"], p["cy"], p["size"], p["r"], png)
        inputs += ["-i", png]; idx = len(inputs)//2 - 1
        en = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in p["ranges"])
        x, y = p["center"][0]-p["r"], p["center"][1]-p["r"]
        fc.append(f"{cur}[{idx}:v]overlay={x}:{y}:enable='{en}'[p{i}]"); cur = f"[p{i}]"
    # ---- 3. 全畫面替換片段（照片＋重繪字幕） ----
    segs = sorted(plan.get("full", []), key=lambda s: s["start"])
    clips = []
    for i, s in enumerate(segs):
        length = s["end"] - s["start"]; frames = int(round(length*fps))
        inputs += ["-i", s["image"]]; idx = len(inputs)//2 - 1
        fx, fy = s.get("focus", [0.5, 0.5])
        # 前景：等比縮放到至少填滿寬度的 (1+zoom) 倍，依 focus 取景，再做慢速推鏡
        f = (f"[{idx}:v]split[bg{i}][fg{i}];"
             f"[bg{i}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=30,eq=brightness=-0.2[bgo{i}];"
             # 近方形/橫向照片：以高度 {int(H*0.72)} 為準縮放再依 focus 裁成 {W} 寬；直向照片：以寬度為準
             f"[fg{i}]scale='if(lt(ih/iw,1.25),-2,{W})':'if(lt(ih/iw,1.25),{int(H*0.72)},-2)',"
             f"crop='min(iw,{W})':ih:'(iw-min(iw,{W}))*{fx}':0[fgs{i}];"
             f"[bgo{i}][fgs{i}]overlay=(W-w)/2:'if(gte(h,H),min(0,max(H-h,H/2-h*{fy})),(H-h)/2)'[comp{i}];"
             f"[comp{i}]zoompan=z='min(zoom+0.0005,1.10)':d={frames}:x='iw*{fx}-(iw/zoom)*{fx}':y='ih*{fy}-(ih/zoom)*{fy}':s={W}x{H}:fps={fps},"
             f"trim=duration={length:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p")
        for (a, b, text) in s.get("captions", []):
            la, lb = max(0, a - s["start"]), min(length, b - s["start"])
            f += (f",drawtext=fontfile='{FONT}':text='{esc(text)}':fontsize={plan.get('caption_size',40)}:fontcolor=white:"
                  f"borderw=3:bordercolor=black:x=(w-text_w)/2:y={plan.get('caption_y',800)}:enable='between(t,{la:.2f},{lb:.2f})'")
        fc.append(f + f"[img{i}]"); clips.append(f"[img{i}]")
    # ---- 4. 保留段切片 + 串接 ----
    keeps, parts, cursor = [], [], 0.0
    for i, s in enumerate(segs):
        if s["start"] > cursor + 0.02: keeps.append((cursor, s["start"], f"[keep{i}]")); parts.append(f"[keep{i}]")
        parts.append(clips[i]); cursor = s["end"]
    if cursor < end - 0.02: keeps.append((cursor, end, "[keepend]")); parts.append("[keepend]")
    fc.append(f"{cur}split={len(keeps)}" + "".join(f"[s{k}]" for k in range(len(keeps))))
    for k, (a, b, lab) in enumerate(keeps):
        fc.append(f"[s{k}]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS{lab}")
    fc.append("".join(parts) + f"concat=n={len(parts)}:v=1:a=0[vcat]")
    last = "[vcat]"
    # ---- 5. 出處 / 額外字幕 ----
    for j, c in enumerate(plan.get("texts", [])):
        fc.append(f"{last}drawtext=fontfile='{FONT}':text='{esc(c['text'])}':fontsize={c.get('size',24)}:fontcolor=white@0.95:"
                  f"borderw=2:bordercolor=black:line_spacing=8:x=(w-text_w)/2:y={c.get('y','h-120')}:enable='between(t,{c['start']:.2f},{c['end']:.2f})'[t{j}]")
        last = f"[t{j}]"
    fc.append(f"[0:a]atrim=0:{end:.3f},asetpts=PTS-STARTPTS[aout]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-stats", *inputs,
           "-filter_complex", ";".join(fc), "-map", last, "-map", "[aout]",
           "-c:v", "libx264", "-preset", plan.get("preset", "medium"), "-crf", str(plan.get("crf", 18)),
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    open(os.path.join(tmp, "ffmpeg_cmd.txt"), "w").write(" ".join(shlex.quote(c) for c in cmd))
    subprocess.check_call(cmd)

if __name__ == "__main__":
    main()
