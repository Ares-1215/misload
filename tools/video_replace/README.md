# video_replace

把短影音中的「真人講解」畫面換成球員圖片、去浮水印、裁片尾，保留原音軌與 9:16。

- `compose.py plan.json`：一次完成 去浮水印/去 logo（delogo）、圓形小視窗換成球員頭像（可多段時間、多位置）、
  主持人全畫面片段換成照片（模糊背景＋慢速推鏡＋重繪字幕）、裁掉片尾、片尾出處字幕。
- `replace_segments.py`：早期簡化版，只做全畫面片段替換。
- `plan.example.json`：抖音「天龙八图／火箭」那支影片實際使用的參數（座標依 720x1280 量測）。

需求：ffmpeg、python3、numpy、opencv-python-headless、系統中文字型（預設文泉驛正黑）。
照片請用 CC BY / CC0 授權（Wikimedia Commons），並在影片說明欄保留出處。
