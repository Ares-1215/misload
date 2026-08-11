# -*- coding: utf-8 -*-
"""解析 OneDrive\誤裝誤訂 內尚未入庫的 xlsx → 產出 JSON 批次檔
用法： python parse_misload.py [來源資料夾] [輸出資料夾]
狀態檔 .uploaded.json 記錄已入庫的 檔名+mtime，重跑只處理新檔/改過的檔。
"""
import openpyxl, sys, json, glob, os, re, warnings, datetime
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

SRC_DIR = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\26516\OneDrive\誤裝誤訂"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SRC_DIR, ".payloads")
STATE = os.path.join(SRC_DIR, ".uploaded.json")
PASSCODE = "8036"
BATCH = 800
os.makedirs(OUT_DIR, exist_ok=True)

def ymd(v):
    if v is None: return None
    if isinstance(v, datetime.datetime): return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None

def hms(v):
    if v is None: return None
    s = str(v).strip().split(".")[0]
    if re.fullmatch(r"\d{5,6}", s):
        s = s.zfill(6)
        return f"{s[0:2]}:{s[2:4]}:{s[4:6]}"
    return s or None

def txt(v):
    if v is None: return None
    s = str(v).strip().replace("\u3000", " ").strip()
    return s or None

def parse_file(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["統計表"]
    date_cols = []
    for c in range(6, ws.max_column + 1):
        v = ws.cell(3, c).value
        if isinstance(v, datetime.datetime):
            date_cols.append((c, v.strftime("%Y-%m-%d")))
    stats = []
    for r in range(5, ws.max_row + 1):
        b, cname, dname = ws.cell(r, 2).value, txt(ws.cell(r, 3).value), txt(ws.cell(r, 4).value)
        if cname is None and dname is None: break
        if cname == "全公司":
            scope, code, region, station = "company", 0, "全公司", ""
        elif dname is None:
            scope, code, region, station = "region", int(b), cname, ""
        elif str(b) == "0" or b == 0:
            scope, code, region, station = "special", 0, "特殊站", dname
        else:
            scope, code, region, station = "station", int(b), cname, dname
        for col, d in date_cols:
            sent = ws.cell(r, col).value
            err = ws.cell(r, col + 1).value
            sent = int(sent) if isinstance(sent, (int, float)) else 0
            err = int(err) if isinstance(err, (int, float)) else 0
            if sent == 0 and err == 0: continue
            stats.append({"stat_date": d, "scope": scope, "region_code": code,
                          "region_name": region, "station_name": station,
                          "sent_count": sent, "err_count": err})
    ws2 = wb["誤裝訂明細"]
    details = {}
    for r in range(5, ws2.max_row + 1):
        seq = ws2.cell(r, 4).value
        send_d = ymd(ws2.cell(r, 9).value)
        if not isinstance(seq, (int, float)) or send_d is None: continue
        row = {
            "region_code": int(ws2.cell(r, 1).value) if isinstance(ws2.cell(r, 1).value, (int, float)) else None,
            "region_name": txt(ws2.cell(r, 3).value),
            "resp_station": txt(ws2.cell(r, 5).value),
            "seq": int(seq),
            "work_date": ymd(ws2.cell(r, 6).value),
            "work_time": hms(ws2.cell(r, 7).value),
            "tracking_no": txt(ws2.cell(r, 8).value),
            "send_station": txt(ws2.cell(r, 10).value),
            "sender": txt(ws2.cell(r, 11).value),
            "address": txt(ws2.cell(r, 12).value),
            "pieces": int(ws2.cell(r, 13).value) if isinstance(ws2.cell(r, 13).value, (int, float)) else None,
            "dest_station": txt(ws2.cell(r, 14).value),
            "note_station": txt(ws2.cell(r, 15).value),
            "note_code": txt(ws2.cell(r, 17).value),
            "note_date": ymd(ws2.cell(r, 18).value),
            "note_time": hms(ws2.cell(r, 19).value),
            "note_staff": txt(ws2.cell(r, 20).value),
            "reply": txt(ws2.cell(r, 21).value),
            "product_type": txt(ws2.cell(r, 22).value),
        }
        details.setdefault(send_d, []).append(row)
    return stats, details

state = {}
if os.path.exists(STATE):
    with open(STATE, encoding="utf-8-sig") as f:
        state = json.load(f)

manifest = []
processed = []
for path in sorted(glob.glob(os.path.join(SRC_DIR, "2026*發送誤裝訂統計表.xlsx"))):
    name = os.path.basename(path)
    mtime = int(os.path.getmtime(path))
    if state.get(name) == mtime:
        continue
    m = re.search(r"(\d{8})", name)
    file_date = f"{m.group(1)[0:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
    stats, details = parse_file(path)
    tag = m.group(1)
    for i in range(0, len(stats), BATCH):
        fn = os.path.join(OUT_DIR, f"{tag}_stats_{i//BATCH}.json")
        with open(fn, "w", encoding="utf-8") as f:
            json.dump({"passcode": PASSCODE, "action": "upload_stats", "rows": stats[i:i+BATCH]}, f, ensure_ascii=False)
        manifest.append(fn)
    total = 0
    for send_d, rows in details.items():
        total += len(rows)
        for i in range(0, len(rows), BATCH):
            fn = os.path.join(OUT_DIR, f"{tag}_det_{send_d}_{i//BATCH}.json")
            with open(fn, "w", encoding="utf-8") as f:
                json.dump({"passcode": PASSCODE, "action": "upload_details", "send_date": send_d,
                           "first": i == 0, "rows": rows[i:i+BATCH]}, f, ensure_ascii=False)
            manifest.append(fn)
    fn = os.path.join(OUT_DIR, f"{tag}_log.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump({"passcode": PASSCODE, "action": "log_upload", "file_date": file_date,
                   "detail_count": total, "stats_days": len(set(s["stat_date"] for s in stats))}, f, ensure_ascii=False)
    manifest.append(fn)
    processed.append((name, mtime))
    print(f"{name}: stats={len(stats)} details={total} dates={sorted(details.keys())}")

with open(os.path.join(OUT_DIR, "manifest.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(manifest))
with open(os.path.join(OUT_DIR, "pending_state.json"), "w", encoding="utf-8") as f:
    json.dump({"state_file": STATE, "old": state, "new": dict(processed)}, f, ensure_ascii=False)
print(f"new_files={len(processed)} payloads={len(manifest)}")
